# Agentic LMS (Project 10)

A prototype Learning Management System in which an AI agent recommends and, with the user's confirmation, executes the student's next action.

## Structure

- `docs/process_model.md` – process model (states, activities, preconditions, recommendation rule)
- `backend/app/process_model.py` – state derivation from the event log, preconditions, baseline recommendation
- `backend/app/forms.py` – **form registry**: one form description = validation + MCP tool + instructions for front-end automation
- `backend/app/main.py` – FastAPI app (login, courses, forms, event log, recommendation)
- `backend/app/seed.py` – demo data
- `backend/tests/test_smoke.py` – end-to-end flow test

## Running

```bash
cd backend
pip install -r requirements.txt
python -m app.seed            # demo data (ana@lms.test / nastavnik@lms.test, password: test)
uvicorn app.main:app --reload # http://localhost:8000/docs
pytest
```

For PostgreSQL: `DATABASE_URL=postgresql+psycopg://user:pass@localhost/lms` (and `pip install psycopg[binary]`).

## Key endpoints

| Endpoint | Purpose |
|---|---|
| `GET /api/forms` | machine-readable description of all forms (source for MCP tools) |
| `POST /api/forms/{name}` | execute a form; `actor` is `user` or `agent`; process preconditions are enforced |
| `GET /api/courses/{id}/state` | derived state of the student in a course |
| `GET /api/courses/{id}/next` | recommendation (currently the baseline rule, later the LLM agent) |
| `GET /api/events` | the user's event log |

## Next steps

1. Synthetic event log generator with labels (and trap scenarios)
2. MCP server on top of `FORMS` (tools generated from `describe()`)
3. LLM agent (variants 1/2/3 for evaluation)
4. React front end with an engine that visibly fills in forms
