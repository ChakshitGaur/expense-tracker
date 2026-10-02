# Expense Tracker

A Django app to log expenses, organise them by category, and see where your money goes.

## Features
- Sign up / log in (each user only sees their own data)
- Add, edit, delete expenses; filter by month and category; pagination
- Per-user categories
- Dashboard: this month's total, spending by category (doughnut), last 6 months (bar)
- CSV import (partial success with per-line errors) and export

## Run it
```
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python manage.py migrate
python manage.py runserver
```
Open http://127.0.0.1:8000 and sign up.

## Test it
```
python manage.py test
```

## CSV format
`date` (YYYY-MM-DD), `amount`, `category` (optional), `description` (optional).

## Layout
- `expenses/models.py` – Category, Expense
- `expenses/services.py` – dashboard aggregation and CSV logic (no HTTP)
- `expenses/views.py`, `forms.py`, `urls.py` – web layer
