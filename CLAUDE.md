# Expense Tracker

Django 6 app, single app `expenses`, SQLite.

## Commands
- Use the venv: `.venv\Scripts\python manage.py <cmd>`
- Tests: `.venv\Scripts\python manage.py test`
- Run: `.venv\Scripts\python manage.py runserver`

## Conventions
- Business logic (aggregation, CSV) lives in `expenses/services.py`, not in views.
- Every query on Expense/Category must be filtered by `request.user`; other users' objects should 404.
- Add a test for every new view or service function.
- Never commit `db.sqlite3` or `.env`.
