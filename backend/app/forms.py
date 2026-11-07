"""Form registry: ONE form description (name, purpose, fields) serves as
  (1) request validation,
  (2) an MCP tool (input schema) — see GET /api/forms,
  (3) instructions for visible front-end automation (the fields to fill in).
A new form = a new entry in FORMS, no agent changes.
"""
from dataclasses import dataclass
from datetime import datetime
from typing import Callable

from sqlalchemy.orm import Session

from .db import utcnow
from .models import (
    Announcement,
    Assignment,
    Enrollment,
    Event,
    Grade,
    Material,
    Submission,
)
from .process_model import check_allowed


@dataclass
class FormField:
    name: str
    type: str  # "integer" | "string"
    description: str
    required: bool = True


@dataclass
class FormSpec:
    name: str  # = activity name = MCP tool name
    title: str
    purpose: str
    role: str  # "student" | "teacher"
    mutating: bool  # true -> the agent asks for user confirmation
    route: str  # front-end page path where the form lives
    fields: list[FormField]
    handler: Callable[[Session, object, dict], dict]

    def describe(self) -> dict:
        """Machine-readable description (also the JSON Schema for the MCP tool)."""
        return {
            "name": self.name,
            "title": self.title,
            "description": self.purpose,
            "role": self.role,
            "mutating": self.mutating,
            "route": self.route,
            "inputSchema": {
                "type": "object",
                "properties": {
                    f.name: {"type": f.type, "description": f.description} for f in self.fields
                },
                "required": [f.name for f in self.fields if f.required],
            },
        }


# ---- handlers: return {"course_id", "object_type", "object_id", "result"} ----

def _enroll(db, user, p):
    db.add(Enrollment(user_id=user.id, course_id=p["course_id"]))
    return dict(course_id=p["course_id"], object_type="course", object_id=p["course_id"], result={})


def _read_announcement(db, user, p):
    a = db.get(Announcement, p["announcement_id"])
    return dict(course_id=a.course_id, object_type="announcement", object_id=a.id,
                result={"title": a.title, "body": a.body})


def _download_material(db, user, p):
    m = db.get(Material, p["material_id"])
    return dict(course_id=m.course_id, object_type="material", object_id=m.id,
                result={"title": m.title, "lesson_no": m.lesson_no, "content": m.content})


def _submit_assignment(db, user, p):
    a = db.get(Assignment, p["assignment_id"])
    db.add(Submission(assignment_id=a.id, user_id=user.id, text=p.get("text", "")))
    return dict(course_id=a.course_id, object_type="assignment", object_id=a.id, result={})


def _view_grade(db, user, p):
    a = db.get(Assignment, p["assignment_id"])
    g = (
        db.query(Grade)
        .filter(Grade.user_id == user.id, Grade.assignment_id == a.id)
        .order_by(Grade.id.desc())
        .first()
    )
    return dict(course_id=a.course_id, object_type="assignment", object_id=a.id,
                result={"assignment": a.title, "value": g.value})


def _post_announcement(db, user, p):
    a = Announcement(course_id=p["course_id"], title=p["title"], body=p.get("body", ""))
    db.add(a)
    db.flush()
    return dict(course_id=a.course_id, object_type="announcement", object_id=a.id, result={"id": a.id})


def _post_material(db, user, p):
    m = Material(course_id=p["course_id"], lesson_no=p["lesson_no"], title=p["title"],
                 content=p.get("content", ""))
    db.add(m)
    db.flush()
    return dict(course_id=m.course_id, object_type="material", object_id=m.id, result={"id": m.id})


def _post_grade(db, user, p):
    g = Grade(assignment_id=p["assignment_id"], user_id=p["student_id"], value=p["value"])
    db.add(g)
    db.flush()
    return dict(course_id=p["course_id"], object_type="assignment", object_id=p["assignment_id"],
                result={"id": g.id})


F = FormField
FORMS: dict[str, FormSpec] = {
    s.name: s
    for s in [
        FormSpec("enroll_course", "Upis na kurs", "Upisuje studenta na izabrani kurs.",
                 "student", True, "/courses/{course_id}",
                 [F("course_id", "integer", "ID kursa")], _enroll),
        FormSpec("read_announcement", "Čitanje obaveštenja",
                 "Otvara obaveštenje na kursu i beleži da je pročitano.",
                 "student", False, "/announcements/{announcement_id}",
                 [F("announcement_id", "integer", "ID obaveštenja")], _read_announcement),
        FormSpec("download_material", "Preuzimanje materijala",
                 "Otvara stranicu materijala lekcije i preuzima ga.",
                 "student", False, "/materials/{material_id}",
                 [F("material_id", "integer", "ID materijala")], _download_material),
        FormSpec("submit_assignment", "Predaja zadatka",
                 "Predaje rešenje zadatka pre isteka roka.",
                 "student", True, "/assignments/{assignment_id}",
                 [F("assignment_id", "integer", "ID zadatka"),
                  F("text", "string", "Tekst rešenja", required=False)], _submit_assignment),
        FormSpec("view_grade", "Pregled ocene", "Prikazuje ocenu za zadatak.",
                 "student", False, "/assignments/{assignment_id}/grade",
                 [F("assignment_id", "integer", "ID zadatka")], _view_grade),
        FormSpec("post_announcement", "Objava obaveštenja", "Nastavnik objavljuje obaveštenje na kursu.",
                 "teacher", True, "/teach/{course_id}/announcements/new",
                 [F("course_id", "integer", "ID kursa"), F("title", "string", "Naslov"),
                  F("body", "string", "Tekst", required=False)], _post_announcement),
        FormSpec("post_material", "Objava materijala", "Nastavnik postavlja materijal za lekciju.",
                 "teacher", True, "/teach/{course_id}/materials/new",
                 [F("course_id", "integer", "ID kursa"), F("lesson_no", "integer", "Redni broj lekcije"),
                  F("title", "string", "Naslov"), F("content", "string", "Sadržaj", required=False)],
                 _post_material),
        FormSpec("post_grade", "Unos ocene", "Nastavnik ocenjuje predat zadatak studenta.",
                 "teacher", True, "/teach/{course_id}/grades/new",
                 [F("course_id", "integer", "ID kursa"), F("assignment_id", "integer", "ID zadatka"),
                  F("student_id", "integer", "ID studenta"), F("value", "integer", "Ocena (poeni)")],
                 _post_grade),
    ]
}


class FormError(Exception):
    def __init__(self, status: int, message: str):
        self.status, self.message = status, message


def _coerce(spec: FormSpec, params: dict) -> dict:
    out = {}
    for f in spec.fields:
        if f.name not in params or params[f.name] is None:
            if f.required:
                raise FormError(422, f"Nedostaje polje: {f.name}")
            continue
        v = params[f.name]
        try:
            out[f.name] = int(v) if f.type == "integer" else str(v)
        except (TypeError, ValueError):
            raise FormError(422, f"Polje {f.name} mora biti tipa {f.type}")
    return out


def execute_form(db: Session, user, name: str, params: dict, actor: str = "user") -> dict:
    """The single entry point for executing an action: validation -> process preconditions ->
    handler -> event log entry. Used by both the UI (actor=user) and the agent (actor=agent)."""
    spec = FORMS.get(name)
    if spec is None:
        raise FormError(404, "Nepoznata forma.")
    if spec.role != user.role:
        raise FormError(403, "Forma nije dostupna za tvoju ulogu.")
    p = _coerce(spec, params)
    ok, reason = check_allowed(db, name, user, p)
    if not ok:
        raise FormError(409, reason)
    out = spec.handler(db, user, p)
    db.add(Event(user_id=user.id, actor=actor, activity=name, course_id=out["course_id"],
                 object_type=out["object_type"], object_id=out["object_id"], ts=utcnow(),
                 payload={k: v for k, v in p.items() if k != "text"}))
    db.commit()
    return out["result"]
