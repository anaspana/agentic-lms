"""Demo podaci: python -m app.seed  (briše i ponovo pravi bazu)."""
from datetime import timedelta

from .db import Base, SessionLocal, engine, utcnow
from .models import Announcement, Assignment, Course, Material, User


def seed():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    db = SessionLocal()
    now = utcnow()
    teacher = User(name="Goran", email="nastavnik@lms.test", password="test", role="teacher")
    ana = User(name="Ana", email="ana@lms.test", password="test", role="student")
    db.add_all([teacher, ana])
    db.flush()
    course = Course(title="Savremene obrazovne tehnologije i standardi", teacher_id=teacher.id)
    other = Course(title="Uvod u procesno rudarenje", teacher_id=teacher.id)
    db.add_all([course, other])
    db.flush()
    db.add_all([
        Announcement(course_id=course.id, title="Dobrodošli na kurs", body="Prvi termin je u ponedeljak.",
                     posted_at=now - timedelta(days=10)),
        Material(course_id=course.id, lesson_no=1, title="Lekcija 1: Uvod", content="...",
                 posted_at=now - timedelta(days=9)),
        Material(course_id=course.id, lesson_no=2, title="Lekcija 2: LMS standardi", content="...",
                 posted_at=now - timedelta(days=5)),
        Material(course_id=course.id, lesson_no=3, title="Lekcija 3: Agenti u obrazovanju", content="...",
                 posted_at=now - timedelta(days=2)),
        Assignment(course_id=course.id, title="Zadatak 1: Pregled literature", due_at=now + timedelta(days=7),
                   posted_at=now - timedelta(days=3)),
    ])
    db.commit()
    db.close()
    print("Seed gotov. Nalozi: ana@lms.test / nastavnik@lms.test (lozinka: test)")


if __name__ == "__main__":
    seed()
