import io
from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from . import services
from .models import Budget, Category, Expense

User = get_user_model()


class BaseTestCase(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("alice", password="pw-12345-xyz")
        self.other = User.objects.create_user("bob", password="pw-12345-xyz")
        self.client.login(username="alice", password="pw-12345-xyz")


class AuthTests(TestCase):
    def test_pages_require_login(self):
        for name in ["dashboard", "expense_list", "expense_add", "category_list", "export_csv", "import_csv"]:
            resp = self.client.get(reverse(name))
            self.assertEqual(resp.status_code, 302, name)
            self.assertIn("/accounts/login/", resp["Location"])

    def test_signup_logs_in(self):
        resp = self.client.post(reverse("signup"), {
            "username": "carol", "password1": "S3cure-pass-987", "password2": "S3cure-pass-987",
        })
        self.assertRedirects(resp, reverse("dashboard"))
        self.assertTrue(User.objects.filter(username="carol").exists())


class ExpenseCrudTests(BaseTestCase):
    def test_create_expense(self):
        cat = Category.objects.create(user=self.user, name="Food")
        resp = self.client.post(reverse("expense_add"), {
            "date": "2026-01-15", "amount": "12.50", "category": cat.pk, "description": "Lunch",
        })
        self.assertRedirects(resp, reverse("expense_list"))
        e = Expense.objects.get()
        self.assertEqual((e.user, e.amount, e.category), (self.user, Decimal("12.50"), cat))

    def test_rejects_non_positive_amount(self):
        resp = self.client.post(reverse("expense_add"), {"date": "2026-01-15", "amount": "0"})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(Expense.objects.count(), 0)

    def test_cannot_use_other_users_category(self):
        theirs = Category.objects.create(user=self.other, name="Secret")
        resp = self.client.post(reverse("expense_add"), {
            "date": "2026-01-15", "amount": "5", "category": theirs.pk,
        })
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(Expense.objects.count(), 0)

    def test_cannot_touch_other_users_expense(self):
        e = Expense.objects.create(user=self.other, amount=Decimal("9"), date=date(2026, 1, 1))
        for name in ["expense_edit", "expense_delete"]:
            self.assertEqual(self.client.get(reverse(name, args=[e.pk])).status_code, 404)
            self.assertEqual(self.client.post(reverse(name, args=[e.pk])).status_code, 404)
        self.assertTrue(Expense.objects.filter(pk=e.pk).exists())

    def test_delete_own_expense(self):
        e = Expense.objects.create(user=self.user, amount=Decimal("9"), date=date(2026, 1, 1))
        self.client.post(reverse("expense_delete", args=[e.pk]))
        self.assertFalse(Expense.objects.exists())

    def test_list_only_shows_own_and_filters(self):
        food = Category.objects.create(user=self.user, name="Food")
        Expense.objects.create(user=self.user, amount=1, date=date(2026, 1, 5), category=food, description="mine-jan")
        Expense.objects.create(user=self.user, amount=2, date=date(2026, 2, 5), description="mine-feb")
        Expense.objects.create(user=self.other, amount=3, date=date(2026, 1, 5), description="theirs")
        body = self.client.get(reverse("expense_list")).content.decode()
        self.assertIn("mine-jan", body)
        self.assertNotIn("theirs", body)
        body = self.client.get(reverse("expense_list"), {"month": "2026-02"}).content.decode()
        self.assertIn("mine-feb", body)
        self.assertNotIn("mine-jan", body)
        body = self.client.get(reverse("expense_list"), {"category": food.pk}).content.decode()
        self.assertIn("mine-jan", body)
        self.assertNotIn("mine-feb", body)

    def test_garbage_filters_do_not_crash(self):
        resp = self.client.get(reverse("expense_list"), {"month": "abcd-ef", "category": "x"})
        self.assertEqual(resp.status_code, 200)


class CategoryTests(BaseTestCase):
    def test_duplicate_category_rejected_case_insensitive(self):
        Category.objects.create(user=self.user, name="Food")
        self.client.post(reverse("category_list"), {"name": "food"})
        self.assertEqual(Category.objects.filter(user=self.user).count(), 1)

    def test_same_name_allowed_for_different_users(self):
        Category.objects.create(user=self.other, name="Food")
        self.client.post(reverse("category_list"), {"name": "Food"})
        self.assertEqual(Category.objects.filter(name="Food").count(), 2)

    def test_delete_category_keeps_expenses(self):
        cat = Category.objects.create(user=self.user, name="Food")
        e = Expense.objects.create(user=self.user, amount=1, date=date(2026, 1, 1), category=cat)
        self.client.post(reverse("category_delete", args=[cat.pk]))
        e.refresh_from_db()
        self.assertIsNone(e.category)

    def test_cannot_delete_other_users_category(self):
        cat = Category.objects.create(user=self.other, name="Food")
        self.assertEqual(self.client.post(reverse("category_delete", args=[cat.pk])).status_code, 404)


class DashboardTests(BaseTestCase):
    def test_dashboard_data(self):
        food = Category.objects.create(user=self.user, name="Food")
        today = date(2026, 3, 15)
        Expense.objects.create(user=self.user, amount=Decimal("10"), date=date(2026, 3, 1), category=food)
        Expense.objects.create(user=self.user, amount=Decimal("5.50"), date=date(2026, 3, 31))
        Expense.objects.create(user=self.user, amount=Decimal("20"), date=date(2026, 1, 10))
        Expense.objects.create(user=self.user, amount=Decimal("99"), date=date(2025, 6, 1))  # outside window
        Expense.objects.create(user=self.other, amount=Decimal("1000"), date=date(2026, 3, 2))
        data = services.dashboard_data(self.user, today=today)
        self.assertEqual(data["month_total"], Decimal("15.50"))
        self.assertEqual(str(data["month_total"]), "15.50")  # SQLite SUM must not leak trailing zeros
        self.assertEqual(str(services.dashboard_data(self.other, today=date(2020, 1, 1))["month_total"]), "0.00")
        self.assertEqual(
            {c["name"]: c["total"] for c in data["by_category"]}, {"Food": 10.0, "Uncategorized": 5.5}
        )
        self.assertEqual([t["month"] for t in data["trend"]],
                         ["Oct 2025", "Nov 2025", "Dec 2025", "Jan 2026", "Feb 2026", "Mar 2026"])
        self.assertEqual([t["total"] for t in data["trend"]], [0, 0, 0, 20.0, 0, 15.5])

    def test_dashboard_renders_empty(self):
        self.assertEqual(self.client.get(reverse("dashboard")).status_code, 200)

    def test_add_months_across_year(self):
        self.assertEqual(services.add_months(date(2026, 1, 1), -1), date(2025, 12, 1))
        self.assertEqual(services.add_months(date(2025, 12, 1), 1), date(2026, 1, 1))


class CsvTests(BaseTestCase):
    def upload(self, text):
        f = SimpleUploadedFile("e.csv", text.encode("utf-8"), content_type="text/csv")
        return self.client.post(reverse("import_csv"), {"file": f})

    def test_export(self):
        cat = Category.objects.create(user=self.user, name="Food")
        Expense.objects.create(user=self.user, amount=Decimal("4.20"), date=date(2026, 1, 2), category=cat, description="Tea")
        Expense.objects.create(user=self.other, amount=Decimal("7"), date=date(2026, 1, 2), description="secret")
        resp = self.client.get(reverse("export_csv"))
        body = resp.content.decode()
        self.assertEqual(resp["Content-Type"], "text/csv")
        self.assertIn("2026-01-02,4.20,Food,Tea", body)
        self.assertNotIn("secret", body)

    def test_import_valid(self):
        resp = self.upload("date,amount,category,description\n2026-01-02,4.20,Food,Tea\n2026-01-03,10,food,Lunch\n")
        self.assertRedirects(resp, reverse("expense_list"))
        self.assertEqual(Expense.objects.filter(user=self.user).count(), 2)
        self.assertEqual(Category.objects.filter(user=self.user).count(), 1)  # case-insensitive reuse

    def test_import_partial_errors(self):
        resp = self.upload("date,amount\n2026-01-02,5\nnot-a-date,5\n2026-01-04,-3\n2026-01-05,abc\n")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(Expense.objects.count(), 1)
        errors = resp.context["errors"]
        self.assertEqual(len(errors), 3)
        self.assertTrue(errors[0].startswith("Line 3"))

    def test_import_missing_columns(self):
        resp = self.upload("foo,bar\n1,2\n")
        self.assertEqual(Expense.objects.count(), 0)
        self.assertIn("Missing column", resp.context["errors"][0])

    def test_roundtrip(self):
        cat = Category.objects.create(user=self.user, name="Food")
        Expense.objects.create(user=self.user, amount=Decimal("4.20"), date=date(2026, 1, 2), category=cat, description="Tea")
        buf = io.StringIO()
        services.export_csv(self.user, buf)
        Expense.objects.all().delete()
        self.upload(buf.getvalue())
        e = Expense.objects.get()
        self.assertEqual((e.amount, e.description, e.category.name), (Decimal("4.20"), "Tea", "Food"))
