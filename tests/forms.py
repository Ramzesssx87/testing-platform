from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User
from .models import Test

class TestSelectionForm(forms.Form):
    test = forms.ModelChoiceField(
        queryset=Test.objects.all().order_by('name'),  # Добавим сортировку по имени
        empty_label="Выберите тест",
        label="Тест"
    )
    
    start_question = forms.IntegerField(
        required=False,
        min_value=1,
        label="Начать с вопроса (необязательно)",
        widget=forms.NumberInput(attrs={'placeholder': 'С какого вопроса начать'})
    )
    end_question = forms.IntegerField(
        required=False,
        min_value=1,
        label="Закончить на вопросе (необязательно)",
        widget=forms.NumberInput(attrs={'placeholder': 'На каком вопросе закончить'})
    )

class CustomUserCreationForm(UserCreationForm):
    email = forms.EmailField(required=True, label="Email")
    
    class Meta:
        model = User
        fields = ("username", "email", "password1", "password2")
    
    def save(self, commit=True):
        user = super().save(commit=False)
        user.email = self.cleaned_data["email"]
        if commit:
            user.save()
        return user

class ExcelUploadForm(forms.Form):
    excel_file = forms.FileField(
        label="Excel файл с тестом",
        help_text="Файл должен соответствовать формату импорта"
    )
    test_name = forms.CharField(
        max_length=255,
        required=False,
        label="Название теста (необязательно)",
        help_text="Если не указано, будет использовано имя файла"
    )