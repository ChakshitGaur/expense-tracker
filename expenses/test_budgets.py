from datetime import date
from decimal import Decimal

from django.urls import reverse
from django.utils import timezone

from . import services
from .models import Budget, Category, Expense
from .tests import BaseTestCase


class BudgetServiceTests(BaseTestCase):
    """budget_status / budget_alert: the maths behind the progress bars and warnings."""

    TODAY = date(2026, 3, 15)

    def setUp(self):
        super().setUp()
        self.food = Category.objects.create(user=self.user, name="Food")
        self.budget = Budget.objects.create(user=self.user, category=self.food, monthly_limit=Decimal("1000"))

    def spend(self, amount, day=date(2026, 3, 5), category=None, user=None):
        return Expense.objects.create(
            user=user or self.user, category=category or self.food, amount=Decimal(amount), date=day
        )

    def status(self):
        rows = services.budget_status(self.user, today=self.TODAY)
        self.assertEqual(len(rows), 1)
        return rows[0]

    def test_no_spending_is_ok_and_zero(self):
        row = self.status()
        self.assertEqual((row["spent"], row["percent"], row["level"]), (Decimal("0.00"), 0, "ok"))

    def test_levels_at_the_boundaries(self):
        cases = [("500", 50, "ok"), ("799.99", 79, "ok"), ("800", 80, "warning"),
                 ("1000", 100, "warning"), ("1000.01", 100, "over")]
        for amount, percent, level in cases:
            Expense.objects.all().delete()
            self.spend(amount)
            row = self.status()
            self.assertEqual((row["percent"], row["level"]), (percent, level), amount)

    def test_percent_rounds_down_never_up(self):
        self.spend("999.99")
        self.assertEqual(self.status()["percent"], 99)

    def test_over_budget_bar_is_capped_and_remaining_is_negative(self):
        self.spend("1500")
        row = self.status()
        self.assertEqual((row["percent"], row["bar_percent"], row["remaining"]), (150, 100, Decimal("-500")))

    def test_only_this_months_spending_in_this_category_for_this_user_counts(self):
        drinks = Category.objects.create(user=self.user, name="Drinks")
        self.spend("100")                                    # counts
        self.spend("100", day=date(2026, 2, 28))             # last month
        self.spend("100", day=date(2026, 4, 1))              # next month
        self.spend("100", category=drinks)                   # other category
        Expense.objects.create(user=self.user, amount=Decimal("100"), date=date(2026, 3, 5))  # uncategorised
        other_food = Category.objects.create(user=self.other, name="Food")
        self.spend("900", category=other_food, user=self.other)  # another user, same category name
        self.assertEqual(self.status()["spent"], Decimal("100.00"))

    def test_rows_are_sorted_most_used_first(self):
        rent = Category.objects.create(user=self.user, name="Rent")
        Budget.objects.create(user=self.user, category=rent, monthly_limit=Decimal("100"))
        self.spend("100")                    # food 10%
        self.spend("90", category=rent)      # rent 90%
        rows = services.budget_status(self.user, today=self.TODAY)
        self.assertEqual([r["category"] for r in rows], ["Rent", "Food"])

    def test_no_budgets_gives_empty_list(self):
        self.assertEqual(services.budget_status(self.other, today=self.TODAY), [])

    def test_alert_levels(self):
        self.spend("500")
        expense = self.spend("300")
        level, text = services.budget_alert(self.user, expense, today=self.TODAY)
        self.assertEqual(level, "warning")
        self.assertIn("80%", text)
        expense = self.spend("300")
        level, text = services.budget_alert(self.user, expense, today=self.TODAY)
        self.assertEqual(level, "over")
        self.assertIn("over budget", text)

    def test_no_alert_when_fine_or_irrelevant(self):
        small = self.spend("10")
        self.assertIsNone(services.budget_alert(self.user, small, today=self.TODAY))
        self.spend("2000")
        old = self.spend("10", day=date(2026, 2, 1))  # last month's expense does not touch this month's budget
        self.assertIsNone(services.budget_alert(self.user, old, today=self.TODAY))
        plain = Expense.objects.create(user=self.user, amount=Decimal("5000"), date=self.TODAY)
        self.assertIsNone(services.budget_alert(self.user, plain, today=self.TODAY))  # no category


class BudgetViewTests(BaseTestCase):
    def setUp(self):
        super().setUp()
        self.food = Category.objects.create(user=self.user, name="Food")

    def test_pages_require_login(self):
        budget = Budget.objects.create(user=self.user, category=self.food, monthly_limit=Decimal("100"))
        self.client.logout()
        for name, args in [("budget_list", []), ("budget_edit", [budget.pk]), ("budget_delete", [budget.pk])]:
            resp = self.client.get(reverse(name, args=args))
            self.assertEqual(resp.status_code, 302, name)
            self.assertIn("/accounts/login/", resp["Location"])

    def test_create_budget(self):
        resp = self.client.post(reverse("budget_list"), {"category": self.food.pk, "monthly_limit": "2500.50"})
        self.assertRedirects(resp, reverse("budget_list"))
        budget = Budget.objects.get()
        self.assertEqual((budget.user, budget.category, budget.monthly_limit),
                         (self.user, self.food, Decimal("2500.50")))

    def test_cannot_budget_someone_elses_category(self):
        theirs = Category.objects.create(user=self.other, name="Secret")
        resp = self.client.post(reverse("budget_list"), {"category": theirs.pk, "monthly_limit": "100"})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(Budget.objects.count(), 0)

    def test_second_budget_for_same_category_is_rejected(self):
        Budget.objects.create(user=self.user, category=self.food, monthly_limit=Decimal("100"))
        self.client.post(reverse("budget_list"), {"category": self.food.pk, "monthly_limit": "999"})
        self.assertEqual(Budget.objects.count(), 1)
        self.assertEqual(Budget.objects.get().monthly_limit, Decimal("100.00"))

    def test_limit_must_be_positive(self):
        for bad in ("0", "-5", "abc", ""):
            resp = self.client.post(reverse("budget_list"), {"category": self.food.pk, "monthly_limit": bad})
            self.assertEqual(resp.status_code, 200, bad)
        self.assertEqual(Budget.objects.count(), 0)

    def test_edit_changes_limit_but_never_the_category(self):
        rent = Category.objects.create(user=self.user, name="Rent")
        budget = Budget.objects.create(user=self.user, category=self.food, monthly_limit=Decimal("100"))
        self.client.post(reverse("budget_edit", args=[budget.pk]), {"category": rent.pk, "monthly_limit": "250"})
        budget.refresh_from_db()
        self.assertEqual((budget.category, budget.monthly_limit), (self.food, Decimal("250.00")))

    def test_other_users_budgets_are_404(self):
        theirs = Category.objects.create(user=self.other, name="Food")
        budget = Budget.objects.create(user=self.other, category=theirs, monthly_limit=Decimal("100"))
        for name in ("budget_edit", "budget_delete"):
            self.assertEqual(self.client.get(reverse(name, args=[budget.pk])).status_code, 404, name)
            self.assertEqual(self.client.post(reverse(name, args=[budget.pk])).status_code, 404, name)
        self.assertTrue(Budget.objects.filter(pk=budget.pk).exists())

    def test_list_shows_only_own_budgets(self):
        theirs = Category.objects.create(user=self.other, name="OtherPersonsCategory")
        Budget.objects.create(user=self.other, category=theirs, monthly_limit=Decimal("100"))
        Budget.objects.create(user=self.user, category=self.food, monthly_limit=Decimal("100"))
        body = self.client.get(reverse("budget_list")).content.decode()
        self.assertIn("Food", body)
        self.assertNotIn("OtherPersonsCategory", body)

    def test_delete_budget_keeps_expenses(self):
        budget = Budget.objects.create(user=self.user, category=self.food, monthly_limit=Decimal("100"))
        Expense.objects.create(user=self.user, category=self.food, amount=Decimal("5"), date=date(2026, 3, 1))
        self.client.post(reverse("budget_delete", args=[budget.pk]))
        self.assertEqual((Budget.objects.count(), Expense.objects.count()), (0, 1))

    def test_deleting_a_category_removes_its_budget(self):
        Budget.objects.create(user=self.user, category=self.food, monthly_limit=Decimal("100"))
        self.client.post(reverse("category_delete", args=[self.food.pk]))
        self.assertEqual(Budget.objects.count(), 0)

    def test_dashboard_shows_budget_progress_and_works_without_budgets(self):
        self.assertContains(self.client.get(reverse("dashboard")), "No budgets yet")
        Budget.objects.create(user=self.user, category=self.food, monthly_limit=Decimal("100"))
        Expense.objects.create(user=self.user, category=self.food, amount=Decimal("90"), date=timezone.localdate())
        resp = self.client.get(reverse("dashboard"))
        self.assertContains(resp, "90.00 / 100.00 (90%)")
        self.assertContains(resp, "near limit")

    def add_expense(self, amount):
        return self.client.post(reverse("expense_add"), {
            "date": timezone.localdate().isoformat(), "amount": amount, "category": self.food.pk, "description": "x",
        }, follow=True)

    def test_adding_expense_shows_warning_then_over_budget_message(self):
        Budget.objects.create(user=self.user, category=self.food, monthly_limit=Decimal("1000"))
        quiet = self.add_expense("100")
        self.assertEqual(list(quiet.context["messages"]), [])
        warned = list(self.add_expense("750").context["messages"])  # 850 of 1000
        self.assertEqual([m.level_tag for m in warned], ["warning"])
        self.assertIn("85%", warned[0].message)
        over = list(self.add_expense("200").context["messages"])  # 1050 of 1000
        self.assertEqual([m.level_tag for m in over], ["error"])
        self.assertIn("over budget", over[0].message)

    def test_no_message_for_category_without_budget(self):
        resp = self.add_expense("99999")
        self.assertEqual(list(resp.context["messages"]), [])
