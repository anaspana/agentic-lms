"""Process engine.

The process itself is described in process/course_lifecycle.yaml. This module
loads that file, derives the student's state from the event log, runs the
condition checks the model refers to and applies its recommendation rules.
"""
from dataclasses import dataclass, field, fields
from pathlib import Path

import yaml
from sqlalchemy import select
from sqlalchemy.orm import Session

from .db import utcnow
from .models import (
    Announcement,
    Assignment,
    Course,
    Enrollment,
    Event,
    Grade,
    Material,
    Submission,
)

MODEL_PATH = Path(__file__).resolve().parent.parent / "process" / "course_lifecycle.yaml"

# Object types used in the model, mapped to database tables.
OBJECT_MODELS = {
    "course": Course,
    "announcement": Announcement,
    "material": Material,
    "assignment": Assignment,
}


# ---- derived state ----

@dataclass
class StudentState:
    user_id: int
    course_id: int
    enrolled: bool = False
    unread_announcements: list[int] = field(default_factory=list)
    pending_materials: list[int] = field(default_factory=list)  # ordered by lesson_no
    open_assignments: list[int] = field(default_factory=list)  # ordered by due date
    unviewed_grades: list[int] = field(default_factory=list)  # assignment ids

    def to_dict(self) -> dict:
        return self.__dict__.copy()


def _done_objects(db: Session, user_id: int, activity: str) -> set[int]:
    rows = db.execute(
        select(Event.object_id).where(Event.user_id == user_id, Event.activity == activity)
    ).scalars()
    return {r for r in rows if r is not None}


def build_state(db: Session, user_id: int, course_id: int) -> StudentState:
    """Where the student is: derived from the event log and the current course content."""
    st = StudentState(user_id=user_id, course_id=course_id)
    st.enrolled = (
        db.execute(
            select(Enrollment.id).where(
                Enrollment.user_id == user_id, Enrollment.course_id == course_id
            )
        ).first()
        is not None
    )
    if not st.enrolled:
        return st

    read = _done_objects(db, user_id, "read_announcement")
    downloaded = _done_objects(db, user_id, "download_material")
    viewed = _done_objects(db, user_id, "view_grade")
    now = utcnow()

    st.unread_announcements = [
        a.id
        for a in db.execute(
            select(Announcement)
            .where(Announcement.course_id == course_id)
            .order_by(Announcement.posted_at, Announcement.id)
        ).scalars()
        if a.id not in read
    ]
    st.pending_materials = [
        m.id
        for m in db.execute(
            select(Material)
            .where(Material.course_id == course_id)
            .order_by(Material.lesson_no, Material.id)
        ).scalars()
        if m.id not in downloaded
    ]
    submitted = set(
        db.execute(select(Submission.assignment_id).where(Submission.user_id == user_id)).scalars()
    )
    st.open_assignments = [
        a.id
        for a in db.execute(
            select(Assignment).where(Assignment.course_id == course_id).order_by(Assignment.due_at)
        ).scalars()
        if a.id not in submitted and a.due_at > now
    ]
    st.unviewed_grades = [
        g.assignment_id
        for g in db.execute(select(Grade).where(Grade.user_id == user_id)).scalars()
        if g.assignment_id not in viewed
        and db.get(Assignment, g.assignment_id).course_id == course_id
    ]
    return st


# ---- conditions ----

class Context:
    """Everything a condition check may need for one activity call."""

    def __init__(self, db: Session, user, activity: str, params: dict, model: dict):
        self.db, self.user, self.params = db, user, params
        obj_type = model["activities"][activity]["object"]
        obj_id = params.get(model["objects"][obj_type]["param"])
        self.obj = db.get(OBJECT_MODELS[obj_type], obj_id) if obj_id is not None else None
        if obj_type == "course":
            self.course = self.obj
        else:
            self.course = db.get(Course, self.obj.course_id) if self.obj else None
        self._state = None

    @property
    def state(self) -> StudentState:
        if self._state is None:
            self._state = build_state(self.db, self.user.id, self.course.id)
        return self._state


def _exists(db, model, **where) -> bool:
    q = select(model.id)
    for col, val in where.items():
        q = q.where(getattr(model, col) == val)
    return db.execute(q).first() is not None


# Each check answers one yes/no question. The model decides which checks
# apply to which activity, so a new activity built from these needs no code.
CONDITIONS = {
    "course_exists": lambda c: c.course is not None,
    "object_exists": lambda c: c.obj is not None,
    "enrolled": lambda c: c.course is not None and c.state.enrolled,
    "not_enrolled": lambda c: c.course is not None and not c.state.enrolled,
    "deadline_open": lambda c: c.obj is not None and c.obj.due_at > utcnow(),
    "not_submitted": lambda c: c.obj is not None
    and not _exists(c.db, Submission, assignment_id=c.obj.id, user_id=c.user.id),
    "grade_exists": lambda c: c.obj is not None
    and _exists(c.db, Grade, assignment_id=c.obj.id, user_id=c.user.id),
    "is_course_teacher": lambda c: c.course is not None and c.course.teacher_id == c.user.id,
    "assignment_in_course": lambda c: c.course is not None
    and _exists(c.db, Assignment, id=c.params.get("assignment_id"), course_id=c.course.id),
    "student_submitted": lambda c: _exists(
        c.db, Submission,
        assignment_id=c.params.get("assignment_id"), user_id=c.params.get("student_id"),
    ),
}


# ---- loading and validation ----

def validate_model(m: dict) -> None:
    """Fail at startup if the model refers to something that does not exist."""
    errors = []
    state_fields = {f.name for f in fields(StudentState)} - {"user_id", "course_id"}
    if set(m["state"]) != state_fields:
        errors.append(f"state must list exactly {sorted(state_fields)}")
    for name in m["conditions"]:
        if name not in CONDITIONS:
            errors.append(f"condition '{name}' has no implementation")
    for name, a in m["activities"].items():
        if a.get("actor") not in ("student", "teacher"):
            errors.append(f"activity '{name}': unknown actor '{a.get('actor')}'")
        if a.get("object") not in m["objects"] or a.get("object") not in OBJECT_MODELS:
            errors.append(f"activity '{name}': unknown object '{a.get('object')}'")
        for cond in a.get("requires", []):
            if cond not in m["conditions"]:
                errors.append(f"activity '{name}': unknown condition '{cond}'")
    for i, rule in enumerate(m["recommendation"]):
        act = m["activities"].get(rule.get("activity"))
        if act is None:
            errors.append(f"recommendation #{i + 1}: unknown activity '{rule.get('activity')}'")
            continue
        key = rule.get("pick_from") or rule.get("unless")
        if key not in m["state"]:
            errors.append(f"recommendation #{i + 1}: unknown state '{key}'")
        if "unless" in rule and act["object"] != "course":
            errors.append(f"recommendation #{i + 1}: 'unless' only works for course activities")
    if errors:
        raise ValueError("Invalid process model:\n  " + "\n  ".join(errors))


def load_model(path: Path = MODEL_PATH) -> dict:
    with open(path, encoding="utf-8") as f:
        model = yaml.safe_load(f)
    validate_model(model)
    return model


MODEL = load_model()


# ---- what the rest of the app uses ----

def check_allowed(db: Session, activity: str, user, params: dict, model: dict = MODEL) -> tuple[bool, str]:
    """Runs the activity's preconditions from the model. Returns (ok, message)."""
    spec = model["activities"].get(activity)
    if spec is None:
        return False, "Nepoznata aktivnost."
    if spec["actor"] != user.role:
        return False, "Ova aktivnost nije dostupna za tvoju ulogu."
    ctx = Context(db, user, activity, params, model)
    for cond in spec["requires"]:
        if not CONDITIONS[cond](ctx):
            return False, model["conditions"][cond]["fail"]
    return True, "ok"


def recommend_next(st: StudentState, model: dict = MODEL) -> dict:
    """Baseline recommendation: the first rule from the model that matches the state."""
    for rule in model["recommendation"]:
        act = model["activities"][rule["activity"]]
        param = model["objects"][act["object"]]["param"]
        if "unless" in rule:
            if not getattr(st, rule["unless"]):
                return {"activity": rule["activity"], "params": {param: st.course_id},
                        "reason": rule["reason"]}
        else:
            items = getattr(st, rule["pick_from"])
            if items:
                return {"activity": rule["activity"], "params": {param: items[0]},
                        "reason": rule["reason"]}
    return {"activity": None, "params": {}, "reason": model["idle_reason"]}
