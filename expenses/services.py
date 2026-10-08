import csv
import io
from datetime import datetime
from decimal import ROUND_FLOOR, Decimal, InvalidOperation

from django.db.models import Sum
from django.db.models.functions import TruncMonth
from django.utils import timezone

from .models import Budget, Category, Expense

CSV_HEADER = ["date", "amount", "category", "description"]
BUDGET_WARNING_PERCENT = 80  # show a warning once this much of a budget is used


def month_start(d):
    return d.replace(day=1)


def add_months(d, n):
    total = d.year * 12 + (d.month - 1) + n
    return d.replace(year=total // 12, month=total % 12 + 1, day=1)


def budget_status(user, today=None):
    """This month's progress for each of the user's budgets, most-used first.

    level: "ok", "warning" (>= BUDGET_WARNING_PERCENT used) or "over" (spent more than the limit).
    Percent is rounded down so 99.9% is never shown as 100%.
    """
    today = today or timezone.localdate()
    start = month_start(today)
    spent_by_category = {
        row["category_id"]: row["total"]
        for row in Expense.objects.filter(
            user=user, category__isnull=False, date__gte=start, date__lt=add_months(start, 1)
        ).values("category_id").annotate(total=Sum("amount"))
    }

    rows = []
    for budget in Budget.objects.filter(user=user).select_related("category"):
        spent = (spent_by_category.get(budget.category_id) or Decimal("0")).quantize(Decimal("0.01"))
        percent = int((spent / budget.monthly_limit * 100).to_integral_value(rounding=ROUND_FLOOR))
        if spent > budget.monthly_limit:
            level = "over"
        elif percent >= BUDGET_WARNING_PERCENT:
            level = "warning"
        else:
            level = "ok"
        rows.append({
            "budget": budget,
            "category": budget.category.name,
            "limit": budget.monthly_limit,
            "spent": spent,
            "remaining": budget.monthly_limit - spent,
            "percent": percent,
            "bar_percent": min(percent, 100),
            "level": level,
        })
    return sorted(rows, key=lambda r: r["percent"], reverse=True)


def budget_alert(user, expense, today=None):
    """After an expense is saved: (level, message) if its category budget needs attention, else None."""
    today = today or timezone.localdate()
    if expense.category_id is None or month_start(expense.date) != month_start(today):
        return None  # only this month's spending counts towards this month's budget
    for row in budget_status(user, today):
        if row["budget"].category_id != expense.category_id or row["level"] == "ok":
            continue
        if row["level"] == "over":
            return "over", (f"{row['category']}: over budget. You've spent {row['spent']} "
                            f"of your {row['limit']} limit this month.")
        return "warning", (f"{row['category']}: you've used {row['percent']}% of your "
                           f"{row['limit']} budget this month.")
    return None


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

    return {
        "month_total": month_total, "by_category": by_category, "trend": trend, "recent": qs[:5],
        "budgets": budget_status(user, today),
    }


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
