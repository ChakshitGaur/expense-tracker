from django.urls import path

from . import views

urlpatterns = [
    path("", views.DashboardView.as_view(), name="dashboard"),
    path("signup/", views.signup, name="signup"),
    path("expenses/", views.ExpenseListView.as_view(), name="expense_list"),
    path("expenses/add/", views.ExpenseCreateView.as_view(), name="expense_add"),
    path("expenses/<int:pk>/edit/", views.ExpenseUpdateView.as_view(), name="expense_edit"),
    path("expenses/<int:pk>/delete/", views.ExpenseDeleteView.as_view(), name="expense_delete"),
    path("categories/", views.CategoryListView.as_view(), name="category_list"),
    path("categories/<int:pk>/delete/", views.CategoryDeleteView.as_view(), name="category_delete"),
    path("budgets/", views.BudgetListView.as_view(), name="budget_list"),
    path("budgets/<int:pk>/edit/", views.BudgetUpdateView.as_view(), name="budget_edit"),
    path("budgets/<int:pk>/delete/", views.BudgetDeleteView.as_view(), name="budget_delete"),
    path("export/", views.export_csv, name="export_csv"),
    path("import/", views.import_csv, name="import_csv"),
]
