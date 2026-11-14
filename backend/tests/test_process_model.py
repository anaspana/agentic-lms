import copy
import os
from datetime import timedelta

os.environ["DATABASE_URL"] = "sqlite:///./test_lms.db"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.db import SessionLocal, utcnow  # noqa: E402
from app.forms import FORMS  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Assignment, Course  # noqa: E402
from app.process_model import (  # noqa: E402
    CONDITIONS,
    MODEL,
    StudentState,
    recommend_next,
    validate_model,
)
from app.seed import seed  # noqa: E402

client = TestClient(app)


def login(email):
    r = client.post("/api/login", json={"email": email, "password": "test"})
    return {"Authorization": f"Bearer {r.json()['token']}"}


def do(h, name, params):
    return client.post(f"/api/forms/{name}", headers=h, json={"params": params})


# ---- the model itself ----

def test_model_is_valid_and_matches_forms():
    validate_model(MODEL)
    assert set(MODEL["activities"]) == set(FORMS)
    for a in MODEL["activities"].values():
        assert all(c in CONDITIONS for c in a["requires"])


def test_validation_catches_unknown_condition():
    broken = copy.deepcopy(MODEL)
    broken["activities"]["enroll_course"]["requires"].append("is_full_moon")
    with pytest.raises(ValueError, match="is_full_moon"):
        validate_model(broken)


def test_forms_take_role_and_mutating_from_model():
    assert FORMS["submit_assignment"].mutating is True
    assert FORMS["download_material"].mutating is False
    assert FORMS["post_grade"].role == "teacher"


def test_process_endpoint():
    body = client.get("/api/process").json()
    assert body["process"] == "course_lifecycle"
    assert "download_material" in body["activities"]


# ---- recommendation follows the order in the model ----

def test_recommendation_order_comes_from_model():
    st = StudentState(user_id=1, course_id=1, enrolled=True,
                      pending_materials=[4], open_assignments=[7])
    assert recommend_next(st)["activity"] == "download_material"

    # swap two rules: behaviour changes with no code change
    swapped = copy.deepcopy(MODEL)
    rules = swapped["recommendation"]
    i, j = 2, 3  # download_material, submit_assignment
    rules[i], rules[j] = rules[j], rules[i]
    rec = recommend_next(st, swapped)
    assert rec == {"activity": "submit_assignment", "params": {"assignment_id": 7},
                   "reason": rules[i]["reason"]}


def test_idle_when_nothing_to_do():
    st = StudentState(user_id=1, course_id=1, enrolled=True)
    assert recommend_next(st)["activity"] is None


# ---- preconditions through the API ----

def test_deadline_passed_blocks_submission():
    seed()
    db = SessionLocal()
    late = Assignment(course_id=1, title="Stari zadatak", due_at=utcnow() - timedelta(days=1))
    db.add(late)
    db.commit()
    late_id = late.id
    db.close()

    ana = login("ana@lms.test")
    do(ana, "enroll_course", {"course_id": 1})
    r = do(ana, "submit_assignment", {"assignment_id": late_id})
    assert r.status_code == 409
    assert r.json()["detail"] == MODEL["conditions"]["deadline_open"]["fail"]


def test_teacher_cannot_grade_assignment_from_another_course():
    seed()
    ana, teacher = login("ana@lms.test"), login("nastavnik@lms.test")
    do(ana, "enroll_course", {"course_id": 1})
    do(ana, "submit_assignment", {"assignment_id": 1})
    sid = client.get("/api/me", headers=ana).json()["id"]

    db = SessionLocal()
    other = db.query(Course).filter(Course.id != 1).first().id
    db.close()

    # assignment 1 belongs to course 1, not to the other course
    r = do(teacher, "post_grade", {"course_id": other, "assignment_id": 1,
                                   "student_id": sid, "value": 8})
    assert r.status_code == 409
    assert r.json()["detail"] == MODEL["conditions"]["assignment_in_course"]["fail"]


def test_student_cannot_use_teacher_form():
    seed()
    ana = login("ana@lms.test")
    r = do(ana, "post_material", {"course_id": 1, "lesson_no": 9, "title": "x"})
    assert r.status_code == 403
