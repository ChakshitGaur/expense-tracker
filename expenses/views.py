from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse_lazy
from django.views.generic import CreateView, DeleteView, ListView, TemplateView, UpdateView

from . import services
from .forms import CategoryForm, ExpenseForm, ImportForm, SignUpForm
from .models import Category, Expense


class UserFormKwargsMixin:
    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["user"] = self.request.user
        return kwargs


class OwnedExpenseMixin(LoginRequiredMixin):
    model = Expense

    def get_queryset(self):
        return super().get_queryset().filter(user=self.request.user)


def signup(request):
    form = SignUpForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        login(request, form.save())
        return redirect("dashboard")
    return render(request, "registration/signup.html", {"form": form})


class DashboardView(LoginRequiredMixin, TemplateView):
    template_name = "expenses/dashboard.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx.update(services.dashboard_data(self.request.user))
        return ctx


class ExpenseListView(OwnedExpenseMixin, ListView):
    paginate_by = 20

    def get_queryset(self):
        qs = super().get_queryset().select_related("category")
        month = self.request.GET.get("month", "")
        category = self.request.GET.get("category", "")
        if len(month) == 7 and month[:4].isdigit() and month[5:].isdigit():
            qs = qs.filter(date__year=int(month[:4]), date__month=int(month[5:]))
        if category.isdigit():
            qs = qs.filter(category_id=int(category))
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["categories"] = Category.objects.filter(user=self.request.user)
        ctx["month"] = self.request.GET.get("month", "")
        ctx["selected_category"] = self.request.GET.get("category", "")
        return ctx


class ExpenseCreateView(LoginRequiredMixin, UserFormKwargsMixin, CreateView):
    model = Expense
    form_class = ExpenseForm
    success_url = reverse_lazy("expense_list")

    def form_valid(self, form):
        form.instance.user = self.request.user
        return super().form_valid(form)


class ExpenseUpdateView(OwnedExpenseMixin, UserFormKwargsMixin, UpdateView):
    form_class = ExpenseForm
    success_url = reverse_lazy("expense_list")


class ExpenseDeleteView(OwnedExpenseMixin, DeleteView):
    success_url = reverse_lazy("expense_list")


class CategoryListView(LoginRequiredMixin, UserFormKwargsMixin, CreateView):
    model = Category
    form_class = CategoryForm
    template_name = "expenses/category_list.html"
    success_url = reverse_lazy("category_list")

    def form_valid(self, form):
        form.instance.user = self.request.user
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["categories"] = Category.objects.filter(user=self.request.user)
        return ctx


class CategoryDeleteView(LoginRequiredMixin, DeleteView):
    model = Category
    success_url = reverse_lazy("category_list")

    def get_queryset(self):
        return super().get_queryset().filter(user=self.request.user)


@login_required
def export_csv(request):
    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = 'attachment; filename="expenses.csv"'
    services.export_csv(request.user, response)
    return response


@login_required
def import_csv(request):
    form = ImportForm(request.POST or None, request.FILES or None)
    errors = []
    if request.method == "POST" and form.is_valid():
        created, errors = services.import_csv(request.user, form.cleaned_data["file"])
        if created:
            messages.success(request, f"Imported {created} expense(s).")
            if not errors:
                return redirect("expense_list")
    return render(request, "expenses/import.html", {"form": form, "errors": errors})
