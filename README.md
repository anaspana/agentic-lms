# Agentic LMS (Project 10)

A prototype Learning Management System in which an AI agent recommends and, with the user's confirmation, executes the student's next action.

## Structure

- `docs/process_model.md` – process model explained (states, activities, preconditions, recommendation rule)
- `backend/process/course_lifecycle.yaml` – **the process model itself**, in a declarative form
- `backend/app/process_model.py` – process engine: loads the model, derives state from the event log, checks conditions, baseline recommendation
- `backend/app/forms.py` – **form registry**: one form description = validation + MCP tool + instructions for front-end automation
- `backend/app/main.py` – FastAPI app (login, courses, forms, event log, recommendation)
- `backend/app/seed.py` – demo data
- `backend/tests/` – end-to-end flow test and process model tests

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
| `GET /api/process` | the process model as JSON |
| `GET /api/forms` | machine-readable description of all forms (source for MCP tools) |
| `POST /api/forms/{name}` | execute a form; `actor` is `user` or `agent`; process preconditions are enforced |
| `GET /api/courses/{id}/state` | derived state of the student in a course |
| `GET /api/courses/{id}/next` | recommendation (currently the baseline rule, later the LLM agent) |
| `GET /api/events` | the user's event log |

## Next steps

1. Synthetic scenario generator with labels, including cases where the right answer depends on content, plus an evaluation harness (baseline rule as variant 0)
2. React front end with pages generated from the form descriptions
3. LLM agent and MCP server, with a propose, preview, confirm flow for actions that change state
4. Front-end engine that visibly fills in forms on the agent's behalf
5. External sources (exam dates) and reminders
6. Evaluation runs and results
