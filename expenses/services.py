import csv
import io
from datetime import datetime
from decimal import Decimal, InvalidOperation

from django.db.models import Sum
from django.db.models.functions import TruncMonth
from django.utils import timezone

from .models import Category, Expense

CSV_HEADER = ["date", "amount", "category", "description"]


def month_start(d):
    return d.replace(day=1)


def add_months(d, n):
    total = d.year * 12 + (d.month - 1) + n
    return d.replace(year=total // 12, month=total % 12 + 1, day=1)


def dashboard_data(user, today=None):
    today = today or timezone.localdate()
    this_month = month_start(today)
    qs = Expense.objects.filter(user=user)

    month_qs = qs.filter(date__gte=this_month, date__lt=add_months(this_month, 1))
    month_total = (month_qs.aggregate(t=Sum("amount"))["t"] or Decimal("0")).quantize(Decimal("0.01"))
    by_category = [
        {"name": r["category__name"] or "Uncategorized", "total": float(r["t"])}
        for r in month_qs.values("category__name").annotate(t=Sum("amount")).order_by("-t")
    ]

    start = add_months(this_month, -5)
    sums = {
        r["m"]: r["t"]
        for r in qs.filter(date__gte=start).annotate(m=TruncMonth("date")).values("m").annotate(t=Sum("amount"))
    }
    trend = []
    for i in range(6):
        m = add_months(start, i)
        trend.append({"month": m.strftime("%b %Y"), "total": float(sums.get(m, 0))})

    return {"month_total": month_total, "by_category": by_category, "trend": trend, "recent": qs[:5]}


def export_csv(user, target):
    writer = csv.writer(target)
    writer.writerow(CSV_HEADER)
    for e in Expense.objects.filter(user=user).select_related("category").order_by("date", "id"):
        writer.writerow([e.date.isoformat(), e.amount, e.category.name if e.category else "", e.description])


def import_csv(user, uploaded):
    """Import valid rows; return (created_count, error_messages)."""
    text = io.TextIOWrapper(uploaded.file, encoding="utf-8-sig", newline="")
    reader = csv.DictReader(text)
    missing = {"date", "amount"} - set(reader.fieldnames or [])
    if missing:
        return 0, [f"Missing column(s): {', '.join(sorted(missing))}"]

    created, errors = 0, []
    cats = {c.name.lower(): c for c in Category.objects.filter(user=user)}
    for line, row in enumerate(reader, start=2):
        try:
            date = datetime.strptime(row["date"].strip(), "%Y-%m-%d").date()
            amount = Decimal(row["amount"].strip())
            if amount <= 0:
                raise ValueError("amount must be positive")
            name = (row.get("category") or "").strip()
            category = None
            if name:
                category = cats.get(name.lower())
                if category is None:
                    category = Category.objects.create(user=user, name=name[:50])
                    cats[name.lower()] = category
            Expense.objects.create(
                user=user, date=date, amount=amount, category=category,
                description=(row.get("description") or "").strip()[:200],
            )
            created += 1
        except (ValueError, InvalidOperation, AttributeError) as exc:
            errors.append(f"Line {line}: {exc}")
    return created, errors
