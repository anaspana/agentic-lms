import os

os.environ["DATABASE_URL"] = "sqlite:///./test_lms.db"

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402
from app.seed import seed  # noqa: E402

client = TestClient(app)


def login(email):
    r = client.post("/api/login", json={"email": email, "password": "test"})
    assert r.status_code == 200
    return {"Authorization": f"Bearer {r.json()['token']}"}


def nxt(h, course=1):
    return client.get(f"/api/courses/{course}/next", headers=h).json()


def do(h, name, params, actor="user"):
    return client.post(f"/api/forms/{name}", headers=h, json={"params": params, "actor": actor})


def test_full_flow():
    seed()
    ana, teacher = login("ana@lms.test"), login("nastavnik@lms.test")

    # forms are machine-described
    forms = client.get("/api/forms", headers=ana).json()
    assert {f["name"] for f in forms} >= {"enroll_course", "download_material"}
    assert "inputSchema" in forms[0]

    # not enrolled -> recommendation is enrolling; the precondition blocks other actions
    assert nxt(ana)["activity"] == "enroll_course"
    assert do(ana, "download_material", {"material_id": 1}).status_code == 409

    assert do(ana, "enroll_course", {"course_id": 1}, actor="agent").status_code == 200
    assert do(ana, "enroll_course", {"course_id": 1}).status_code == 409  # already enrolled

    # announcement -> lessons 1..3 -> assignment
    assert nxt(ana)["activity"] == "read_announcement"
    do(ana, "read_announcement", {"announcement_id": 1})
    for i in (1, 2, 3):
        rec = nxt(ana)
        assert (rec["activity"], rec["params"]["material_id"]) == ("download_material", i)
        assert do(ana, "download_material", {"material_id": i}).status_code == 200
    assert nxt(ana)["activity"] == "submit_assignment"
    assert nxt(ana)["mutating"] is True

    # teacher publishes lesson 4 after lesson 3 -> the recommendation jumps to it
    r = do(teacher, "post_material", {"course_id": 1, "lesson_no": 4, "title": "Lekcija 4", "content": "x"})
    assert r.status_code == 200
    rec = nxt(ana)
    assert (rec["activity"], rec["params"]["material_id"]) == ("download_material", r.json()["result"]["id"])
    do(ana, "download_material", {"material_id": r.json()["result"]["id"]})

    # submission, grade (the teacher cannot grade without a submission)
    assert do(teacher, "post_grade", {"course_id": 1, "assignment_id": 1, "student_id": 1, "value": 9}).status_code == 409
    assert do(ana, "submit_assignment", {"assignment_id": 1, "text": "moje"}).status_code == 200
    assert do(ana, "submit_assignment", {"assignment_id": 1}).status_code == 409
    sid = client.get("/api/me", headers=ana).json()["id"]
    assert do(teacher, "post_grade", {"course_id": 1, "assignment_id": 1, "student_id": sid, "value": 9}).status_code == 200
    assert nxt(ana)["activity"] == "view_grade"
    assert do(ana, "view_grade", {"assignment_id": 1}).json()["result"]["value"] == 9
    assert nxt(ana)["activity"] is None

    # event log: every action recorded, with the actor
    ev = client.get("/api/events", headers=ana).json()
    assert ev[0]["activity"] == "enroll_course" and ev[0]["actor"] == "agent"
    # enrollment, announcement, 4 downloads, submission, grade view
    assert len(ev) == 8
