import secrets

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from .db import Base, engine, get_db
from .forms import FORMS, FormError, execute_form
from .models import (
    Announcement,
    Assignment,
    Course,
    Enrollment,
    Event,
    Grade,
    Material,
    User,
)
from .process_model import build_state, recommend_next

Base.metadata.create_all(engine)

app = FastAPI(title="Agentski LMS")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)


def current_user(authorization: str = Header(default=""), db: Session = Depends(get_db)) -> User:
    token = authorization.removeprefix("Bearer ").strip()
    user = db.execute(select(User).where(User.token == token)).scalar_one_or_none() if token else None
    if user is None:
        raise HTTPException(401, "Neprijavljen korisnik.")
    return user


class LoginIn(BaseModel):
    email: str
    password: str


@app.post("/api/login")
def login(body: LoginIn, db: Session = Depends(get_db)):
    user = db.execute(select(User).where(User.email == body.email)).scalar_one_or_none()
    if user is None or user.password != body.password:
        raise HTTPException(401, "Pogrešan email ili lozinka.")
    user.token = secrets.token_hex(16)
    db.commit()
    return {"token": user.token, "user": {"id": user.id, "name": user.name, "role": user.role}}


@app.get("/api/me")
def me(user: User = Depends(current_user)):
    return {"id": user.id, "name": user.name, "role": user.role, "email": user.email}


@app.get("/api/courses")
def courses(user: User = Depends(current_user), db: Session = Depends(get_db)):
    enrolled = set(db.execute(select(Enrollment.course_id).where(Enrollment.user_id == user.id)).scalars())
    return [
        {"id": c.id, "title": c.title, "enrolled": c.id in enrolled}
        for c in db.execute(select(Course).order_by(Course.id)).scalars()
    ]


@app.get("/api/courses/{course_id}")
def course_detail(course_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    c = db.get(Course, course_id)
    if c is None:
        raise HTTPException(404, "Kurs ne postoji.")
    st = build_state(db, user.id, course_id)
    out = {"id": c.id, "title": c.title, "enrolled": st.enrolled}
    if st.enrolled or user.id == c.teacher_id:
        out["announcements"] = [
            {"id": a.id, "title": a.title, "posted_at": a.posted_at.isoformat()}
            for a in db.execute(select(Announcement).where(Announcement.course_id == c.id)
                                .order_by(Announcement.posted_at)).scalars()
        ]
        out["materials"] = [
            {"id": m.id, "lesson_no": m.lesson_no, "title": m.title}
            for m in db.execute(select(Material).where(Material.course_id == c.id)
                                .order_by(Material.lesson_no)).scalars()
        ]
        out["assignments"] = [
            {"id": a.id, "title": a.title, "due_at": a.due_at.isoformat()}
            for a in db.execute(select(Assignment).where(Assignment.course_id == c.id)
                                .order_by(Assignment.due_at)).scalars()
        ]
        out["grades"] = [
            {"assignment_id": g.assignment_id, "value": g.value}
            for g in db.execute(select(Grade).where(Grade.user_id == user.id)).scalars()
        ]
    return out


@app.get("/api/forms")
def list_forms(user: User = Depends(current_user)):
    """Machine-readable description of all forms available to the user's role (source for MCP tools)."""
    return [f.describe() for f in FORMS.values() if f.role == user.role]


class FormIn(BaseModel):
    params: dict = {}
    actor: str = "user"  # "user" | "agent"


@app.post("/api/forms/{name}")
def submit_form(name: str, body: FormIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    if body.actor not in ("user", "agent"):
        raise HTTPException(422, "actor mora biti 'user' ili 'agent'.")
    try:
        return {"ok": True, "result": execute_form(db, user, name, body.params, actor=body.actor)}
    except FormError as e:
        raise HTTPException(e.status, e.message)


@app.get("/api/courses/{course_id}/state")
def course_state(course_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    return build_state(db, user.id, course_id).to_dict()


@app.get("/api/courses/{course_id}/next")
def next_action(course_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Recommendation by the reference (baseline) rule. The LLM agent comes later."""
    rec = recommend_next(build_state(db, user.id, course_id))
    spec = FORMS.get(rec["activity"]) if rec["activity"] else None
    rec["mutating"] = spec.mutating if spec else False
    rec["route"] = spec.route.format(**rec["params"]) if spec else None
    return rec


@app.get("/api/events")
def events(course_id: int | None = None, user: User = Depends(current_user), db: Session = Depends(get_db)):
    q = select(Event).where(Event.user_id == user.id).order_by(Event.ts, Event.id)
    if course_id is not None:
        q = q.where(Event.course_id == course_id)
    return [
        {"id": e.id, "actor": e.actor, "activity": e.activity, "course_id": e.course_id,
         "object_type": e.object_type, "object_id": e.object_id, "ts": e.ts.isoformat()}
        for e in db.execute(q).scalars()
    ]
