"""Model procesa: izvođenje stanja studenta iz event loga + stanja kursa,
provera preduslova i referentna (baseline) preporuka.

Vidi docs/process_model.md.
"""
from dataclasses import dataclass, field

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


@dataclass
class StudentState:
    user_id: int
    course_id: int
    enrolled: bool = False
    unread_announcements: list[int] = field(default_factory=list)
    pending_materials: list[int] = field(default_factory=list)  # po lesson_no
    open_assignments: list[int] = field(default_factory=list)  # po roku
    unviewed_grades: list[int] = field(default_factory=list)  # assignment_id

    def to_dict(self) -> dict:
        return self.__dict__.copy()


def _done_objects(db: Session, user_id: int, activity: str) -> set[int]:
    rows = db.execute(
        select(Event.object_id).where(Event.user_id == user_id, Event.activity == activity)
    ).scalars()
    return {r for r in rows if r is not None}


def build_state(db: Session, user_id: int, course_id: int) -> StudentState:
    """Gde se student nalazi: izvodi se iz event loga i trenutnog stanja kursa."""
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
            select(Announcement).where(Announcement.course_id == course_id).order_by(Announcement.posted_at, Announcement.id)
        ).scalars()
        if a.id not in read
    ]
    st.pending_materials = [
        m.id
        for m in db.execute(
            select(Material).where(Material.course_id == course_id).order_by(Material.lesson_no, Material.id)
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


def check_allowed(db: Session, activity: str, user, params: dict) -> tuple[bool, str]:
    """Preduslovi aktivnosti (tabela u docs/process_model.md)."""
    now = utcnow()
    if user.role == "teacher":
        if activity not in ("post_announcement", "post_material", "post_grade"):
            return False, "Nastavnik ne može da izvrši ovu aktivnost."
        course = db.get(Course, params.get("course_id"))
        if course is None or course.teacher_id != user.id:
            return False, "Nisi nastavnik ovog kursa."
        if activity == "post_grade":
            sub = db.execute(
                select(Submission.id).where(
                    Submission.assignment_id == params.get("assignment_id"),
                    Submission.user_id == params.get("student_id"),
                )
            ).first()
            if sub is None:
                return False, "Student nije predao zadatak."
        return True, "ok"

    # student
    if activity in ("post_announcement", "post_material", "post_grade"):
        return False, "Samo nastavnik može da objavljuje."

    if activity == "enroll_course":
        course = db.get(Course, params.get("course_id"))
        if course is None:
            return False, "Kurs ne postoji."
        if build_state(db, user.id, course.id).enrolled:
            return False, "Već si upisan na ovaj kurs."
        return True, "ok"

    # sve ostalo traži upis; kurs se izvodi iz objekta
    obj_course = _course_of(db, activity, params)
    if obj_course is None:
        return False, "Objekat ne postoji."
    st = build_state(db, user.id, obj_course)
    if not st.enrolled:
        return False, "Prvo se upiši na kurs."
    if activity == "submit_assignment":
        a = db.get(Assignment, params["assignment_id"])
        if a.due_at <= now:
            return False, "Rok za predaju je istekao."
        if a.id not in st.open_assignments:
            return False, "Zadatak je već predat."
    if activity == "view_grade":
        has = db.execute(
            select(Grade.id).where(
                Grade.user_id == user.id, Grade.assignment_id == params["assignment_id"]
            )
        ).first()
        if has is None:
            return False, "Ocena još nije objavljena."
    return True, "ok"


def _course_of(db: Session, activity: str, params: dict) -> int | None:
    model, key = {
        "read_announcement": (Announcement, "announcement_id"),
        "download_material": (Material, "material_id"),
        "submit_assignment": (Assignment, "assignment_id"),
        "view_grade": (Assignment, "assignment_id"),
    }[activity]
    obj = db.get(model, params.get(key))
    return obj.course_id if obj else None


def recommend_next(st: StudentState) -> dict:
    """Referentno (baseline) pravilo preporuke, prioritet kao u docs/process_model.md."""
    if not st.enrolled:
        return {"activity": "enroll_course", "params": {"course_id": st.course_id},
                "reason": "Nisi upisan na kurs."}
    if st.unread_announcements:
        return {"activity": "read_announcement",
                "params": {"announcement_id": st.unread_announcements[0]},
                "reason": "Postoji nepročitano obaveštenje."}
    if st.pending_materials:
        return {"activity": "download_material",
                "params": {"material_id": st.pending_materials[0]},
                "reason": "Nastavnik je objavio materijal koji nisi preuzela."}
    if st.open_assignments:
        return {"activity": "submit_assignment",
                "params": {"assignment_id": st.open_assignments[0]},
                "reason": "Imaš otvoren zadatak sa rokom koji ističe."}
    if st.unviewed_grades:
        return {"activity": "view_grade",
                "params": {"assignment_id": st.unviewed_grades[0]},
                "reason": "Objavljena je ocena koju nisi pogledala."}
    return {"activity": None, "params": {}, "reason": "Nema ništa novo — sve je ažurno."}
