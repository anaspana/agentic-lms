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

    # forme su mašinski opisane
    forms = client.get("/api/forms", headers=ana).json()
    assert {f["name"] for f in forms} >= {"enroll_course", "download_material"}
    assert "inputSchema" in forms[0]

    # neupisan -> preporuka je upis; preduslov blokira ostale akcije
    assert nxt(ana)["activity"] == "enroll_course"
    assert do(ana, "download_material", {"material_id": 1}).status_code == 409

    assert do(ana, "enroll_course", {"course_id": 1}, actor="agent").status_code == 200
    assert do(ana, "enroll_course", {"course_id": 1}).status_code == 409  # već upisana

    # obaveštenje -> lekcije 1..3 -> zadatak
    assert nxt(ana)["activity"] == "read_announcement"
    do(ana, "read_announcement", {"announcement_id": 1})
    for i in (1, 2, 3):
        rec = nxt(ana)
        assert (rec["activity"], rec["params"]["material_id"]) == ("download_material", i)
        assert do(ana, "download_material", {"material_id": i}).status_code == 200
    assert nxt(ana)["activity"] == "submit_assignment"
    assert nxt(ana)["mutating"] is True

    # nastavnik objavi lekciju 4 nakon lekcije 3 -> preporuka skače na nju
    r = do(teacher, "post_material", {"course_id": 1, "lesson_no": 4, "title": "Lekcija 4", "content": "x"})
    assert r.status_code == 200
    rec = nxt(ana)
    assert (rec["activity"], rec["params"]["material_id"]) == ("download_material", r.json()["result"]["id"])
    do(ana, "download_material", {"material_id": r.json()["result"]["id"]})

    # predaja, ocena (nastavnik ne može da oceni bez predaje)
    assert do(teacher, "post_grade", {"course_id": 1, "assignment_id": 1, "student_id": 1, "value": 9}).status_code == 409
    assert do(ana, "submit_assignment", {"assignment_id": 1, "text": "moje"}).status_code == 200
    assert do(ana, "submit_assignment", {"assignment_id": 1}).status_code == 409
    sid = client.get("/api/me", headers=ana).json()["id"]
    assert do(teacher, "post_grade", {"course_id": 1, "assignment_id": 1, "student_id": sid, "value": 9}).status_code == 200
    assert nxt(ana)["activity"] == "view_grade"
    assert do(ana, "view_grade", {"assignment_id": 1}).json()["result"]["value"] == 9
    assert nxt(ana)["activity"] is None

    # event log: svaka akcija zabeležena, sa izvršiocem
    ev = client.get("/api/events", headers=ana).json()
    assert ev[0]["activity"] == "enroll_course" and ev[0]["actor"] == "agent"
    # upis, obaveštenje, 4 preuzimanja, predaja, pregled ocene
    assert len(ev) == 8
