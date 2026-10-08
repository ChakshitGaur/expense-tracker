# Expense Tracker

Django 6 app, single app `expenses`, SQLite.

## Commands
- Use the venv: `.venv\Scripts\python manage.py <cmd>`
- Tests: `.venv\Scripts\python manage.py test`
- Run: `.venv\Scripts\python manage.py runserver` (needs a `.env` with `DJANGO_DEBUG=1`; copy `.env.example`)

## Conventions
- Business logic (aggregation, CSV) lives in `expenses/services.py`, not in views.
- Every query on Expense/Category must be filtered by `request.user`; other users' objects should 404.
- Add a test for every new view or service function.
- CI (`.github/workflows/tests.yml`) runs `check`, a missing-migrations check and the tests on every PR; keep it green.
- Never commit `db.sqlite3` or `.env`.
- Secrets and DEBUG come from environment variables / `.env`; never hard-code a SECRET_KEY.
