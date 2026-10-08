from django import forms
from django.contrib.auth.forms import UserCreationForm

from .models import Budget, Category, Expense


class ExpenseForm(forms.ModelForm):
    class Meta:
        model = Expense
        fields = ["date", "amount", "category", "description"]
        widgets = {"date": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d")}

    def __init__(self, *args, user, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["category"].queryset = Category.objects.filter(user=user)


class CategoryForm(forms.ModelForm):
    class Meta:
        model = Category
        fields = ["name"]

    def __init__(self, *args, user, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user

    def clean_name(self):
        name = self.cleaned_data["name"].strip()
        if Category.objects.filter(user=self.user, name__iexact=name).exists():
            raise forms.ValidationError("You already have this category.")
        return name


class BudgetForm(forms.ModelForm):
    class Meta:
        model = Budget
        fields = ["category", "monthly_limit"]
        labels = {"monthly_limit": "Monthly limit"}

    def __init__(self, *args, user, **kwargs):
        super().__init__(*args, **kwargs)
        field = self.fields["category"]
        if self.instance.pk:  # editing: the category is fixed, only the limit changes
            field.queryset = Category.objects.filter(pk=self.instance.category_id)
            field.disabled = True
        else:  # creating: only the user's own categories that don't have a budget yet
            field.queryset = Category.objects.filter(user=user).exclude(budgets__isnull=False)


class ImportForm(forms.Form):
    file = forms.FileField(help_text="CSV with columns: date, amount, category, description")


class SignUpForm(UserCreationForm):
    pass
