# Agentski LMS (Projekat 10)

Prototip LMS-a u kome AI agent preporučuje i (uz potvrdu) izvršava sledeću akciju studenta.

## Struktura

- `docs/process_model.md` – model procesa (stanja, aktivnosti, preduslovi, pravilo preporuke)
- `backend/app/process_model.py` – izvođenje stanja iz event loga + preduslovi + baseline preporuka
- `backend/app/forms.py` – **registar formi**: jedan opis forme = validacija + MCP alat + uputstvo za front automatizaciju
- `backend/app/main.py` – FastAPI (login, kursevi, forme, event log, preporuka)
- `backend/app/seed.py` – demo podaci
- `backend/tests/test_smoke.py` – test celog toka

## Pokretanje

```bash
cd backend
pip install -r requirements.txt
python -m app.seed            # demo podaci (ana@lms.test / nastavnik@lms.test, lozinka: test)
uvicorn app.main:app --reload # http://localhost:8000/docs
pytest
```

Za PostgreSQL: `DATABASE_URL=postgresql+psycopg://user:pass@localhost/lms` (+ `pip install psycopg[binary]`).

## Ključni endpointi

| Endpoint | Namena |
|---|---|
| `GET /api/forms` | mašinski čitljiv opis formi (izvor za MCP alate) |
| `POST /api/forms/{name}` | izvršenje forme; `actor` = `user` ili `agent`; proverava preduslove procesa |
| `GET /api/courses/{id}/state` | izvedeno stanje studenta na kursu |
| `GET /api/courses/{id}/next` | preporuka (za sada baseline pravilo, kasnije LLM agent) |
| `GET /api/events` | event log korisnika |

## Sledeći koraci

1. Generator sintetičkog event loga sa labelama (+ zamke)
2. MCP server nad `FORMS` (alati se generišu iz `describe()`)
3. LLM agent (varijante 1/2/3 za evaluaciju)
4. React front sa engine-om za vidljivo popunjavanje formi
