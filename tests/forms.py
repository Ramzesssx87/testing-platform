from django import forms
from django.contrib.auth.forms import UserCreationForm, UserChangeForm
from django.contrib.auth.models import User
from .models import Test, UserProfile
from django.utils import timezone

class CustomUserCreationForm(UserCreationForm):
    email = forms.EmailField(required=True, label="Email")
    
    # Убираем старое поле department_code и добавляем новые поля для ФИО
    last_name = forms.CharField(
        max_length=100, 
        required=True, 
        label="Фамилия",
        widget=forms.TextInput(attrs={'placeholder': 'Введите вашу фамилию'})
    )
    first_name = forms.CharField(
        max_length=100, 
        required=True, 
        label="Имя",
        widget=forms.TextInput(attrs={'placeholder': 'Введите ваше имя'})
    )
    patronymic = forms.CharField(
        max_length=100, 
        required=False, 
        label="Отчество",
        widget=forms.TextInput(attrs={'placeholder': 'Введите ваше отчество (необязательно)'})
    )
    
    department_code = forms.CharField(
        max_length=50, 
        required=False, 
        label="Код подразделения",
        help_text="Формат: Группа-Подгруппа-Подподгруппа (например: 35-1-1). Добавьте 'У' для прав просмотра",
        widget=forms.TextInput(attrs={'placeholder': 'Например: 35-1-1'})
    )
    
    class Meta:
        model = User
        fields = ("username", "email", "last_name", "first_name", "patronymic", "department_code", "password1", "password2")
    
    def save(self, commit=True):
        user = super().save(commit=False)
        user.email = self.cleaned_data["email"]
        # Сохраняем стандартные поля User
        user.first_name = self.cleaned_data["first_name"]
        user.last_name = self.cleaned_data["last_name"]
        
        if commit:
            user.save()
            # Сохраняем дополнительные поля в профиль
            if hasattr(user, 'profile'):
                user.profile.patronymic = self.cleaned_data["patronymic"]
                user.profile.department_code = self.cleaned_data["department_code"]
                user.profile.save()
            else:
                UserProfile.objects.create(
                    user=user, 
                    patronymic=self.cleaned_data["patronymic"],
                    department_code=self.cleaned_data["department_code"],
                    first_name=self.cleaned_data["first_name"],
                    last_name=self.cleaned_data["last_name"]
                )
        return user

class UserProfileForm(forms.ModelForm):
    # Добавляем поля ФИО в форму профиля
    last_name = forms.CharField(
        max_length=100, 
        required=True, 
        label="Фамилия",
        widget=forms.TextInput(attrs={'placeholder': 'Введите вашу фамилию'})
    )
    first_name = forms.CharField(
        max_length=100, 
        required=True, 
        label="Имя",
        widget=forms.TextInput(attrs={'placeholder': 'Введите ваше имя'})
    )
    
    class Meta:
        model = UserProfile
        fields = ['last_name', 'first_name', 'patronymic', 'department_code']
        labels = {
            'patronymic': 'Отчество',
            'department_code': 'Код подразделения',
        }
        help_texts = {
            'department_code': 'Формат: Группа-Подгруппа-Подподгруппа (например: 35-1-1). Добавьте "У" для прав просмотра',
        }
        widgets = {
            'patronymic': forms.TextInput(attrs={'placeholder': 'Введите ваше отчество'}),
            'department_code': forms.TextInput(attrs={'placeholder': 'Например: 35-1-1'}),
        }

class UserEditForm(forms.ModelForm):
    # Эта форма теперь будет использоваться только для email
    class Meta:
        model = User
        fields = ['email']
        labels = {
            'email': 'Email',
        }

class TestSelectionForm(forms.Form):
    # существующий код без изменений
    test = forms.ModelChoiceField(
        queryset=Test.objects.all().order_by('name'),
        empty_label="Выберите тест",
        label="Тест"
    )
    
    start_question = forms.IntegerField(
        required=False,
        min_value=1,
        label="Начать с:",
        widget=forms.NumberInput(attrs={'placeholder': 'С какого вопроса начать'})
    )
    end_question = forms.IntegerField(
        required=False,
        min_value=1,
        label="Закончить на:",
        widget=forms.NumberInput(attrs={'placeholder': 'На каком вопросе закончить'})
    )

class ExpressTestForm(forms.Form):
    test = forms.ModelChoiceField(
        queryset=Test.objects.all().order_by('name'),
        empty_label="Выберите тест",
        label="Тест для экспресс-теста"
    )
    question_count = forms.IntegerField(
        min_value=1,
        max_value=100,
        label="Количество вопросов",
        widget=forms.NumberInput(attrs={'placeholder': 'От 1 до 100'})
    )

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

# Функция для проведения зачета 

class QuizCreationForm(forms.Form):
    test = forms.ModelChoiceField(
        queryset=Test.objects.all().order_by('name'),
        empty_label="Выберите тест",
        label="Тест для зачета"
    )
    question_count = forms.IntegerField(
        min_value=5,
        max_value=100,
        initial=20,
        label="Количество вопросов",
        help_text="От 5 до 100 вопросов"
    )
    time_limit_minutes = forms.IntegerField(
        min_value=10,
        max_value=180,
        initial=45,
        label="Лимит времени (минуты)",
        help_text="От 10 до 180 минут"
    )
    starts_at = forms.DateTimeField(
        label="Время начала зачета",
        widget=forms.DateTimeInput(attrs={'type': 'datetime-local'}),
        help_text="Дата и время начала зачета"
    )
    ends_at = forms.DateTimeField(
        label="Время окончания зачета",
        widget=forms.DateTimeInput(attrs={'type': 'datetime-local'}),
        help_text="Дата и время окончания зачета"
    )
    
    def clean(self):
        cleaned_data = super().clean()
        starts_at = cleaned_data.get('starts_at')
        ends_at = cleaned_data.get('ends_at')
        
        if starts_at and ends_at:
            if starts_at >= ends_at:
                raise forms.ValidationError("Время окончания должно быть позже времени начала")
            if starts_at < timezone.now():
                raise forms.ValidationError("Время начала не может быть в прошлом")
        
        return cleaned_data