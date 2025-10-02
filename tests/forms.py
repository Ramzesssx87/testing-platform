from django import forms
from django.contrib.auth.forms import UserCreationForm, UserChangeForm
from django.contrib.auth.models import User
from .models import Test, UserProfile
from django.utils import timezone

class CustomUserCreationForm(UserCreationForm):
    email = forms.EmailField(required=True, label="Email")
    
    class Meta:
        model = User
        fields = ("username", "email", "first_name", "last_name", "password1", "password2")
        labels = {
            'first_name': 'Имя',
            'last_name': 'Фамилия',
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Добавляем поле отчества и кода подразделения
        self.fields['patronymic'] = forms.CharField(
            max_length=100, 
            required=False, 
            label="Отчество",
            widget=forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Введите ваше отчество (необязательно)'
            })
        )
        self.fields['department_code'] = forms.CharField(
            max_length=50, 
            required=False, 
            label="Код подразделения",
            help_text="Формат: Группа-Подгруппа-Подподгруппа (например: 35-1-1)",
            widget=forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Например: 35-1-1'
            })
        )
        
        # Настраиваем обязательные поля
        self.fields['first_name'].required = True
        self.fields['last_name'].required = True
        self.fields['first_name'].widget.attrs.update({
            'class': 'form-control',
            'placeholder': 'Введите ваше имя'
        })
        self.fields['last_name'].widget.attrs.update({
            'class': 'form-control', 
            'placeholder': 'Введите вашу фамилию'
        })
        self.fields['username'].widget.attrs.update({
            'class': 'form-control',
            'placeholder': 'Никнейм'
        })
        self.fields['email'].widget.attrs.update({
            'class': 'form-control',
            'placeholder': 'Введите ваш email'
        })
        self.fields['password1'].widget.attrs.update({
            'class': 'form-control',
            'placeholder': 'Введите пароль'
        })
        self.fields['password2'].widget.attrs.update({
            'class': 'form-control',
            'placeholder': 'Повторите пароль'
        })
    
    def save(self, commit=True):
        user = super().save(commit=False)
        user.email = self.cleaned_data["email"]
        user.first_name = self.cleaned_data.get("first_name", "")
        user.last_name = self.cleaned_data.get("last_name", "")
        
        if commit:
            user.save()
            
            # Получаем или создаем профиль
            profile, created = UserProfile.objects.get_or_create(user=user)
            
            # Сохраняем ВСЕ данные из формы в профиль
            profile.first_name = self.cleaned_data.get("first_name", "")
            profile.last_name = self.cleaned_data.get("last_name", "")
            profile.patronymic = self.cleaned_data.get("patronymic", "")
            profile.department_code = self.cleaned_data.get("department_code", "")
            
            # Сохраняем профиль
            profile.save()
            
            # ОТЛАДОЧНАЯ ИНФОРМАЦИЯ после полного сохранения
            print("=== ПОСЛЕ ПОЛНОГО СОХРАНЕНИЯ ===")
            profile.refresh_from_db()  # Обновляем данные из базы
            print(f"Профиль отчество в БД: {profile.patronymic}")
            print(f"Профиль код в БД: {profile.department_code}")
            
        return user

class UserProfileForm(forms.ModelForm):
    # Используем стандартные поля User для основных данных
    username = forms.CharField(
        max_length=150,
        required=True,
        label="Имя пользователя",
        widget=forms.TextInput(attrs={'placeholder': 'Введите имя пользователя'})
    )
    email = forms.EmailField(
        required=True,
        label="Email",
        widget=forms.EmailInput(attrs={'placeholder': 'Введите ваш email'})
    )
    
    class Meta:
        model = UserProfile
        fields = ['last_name', 'first_name', 'patronymic', 'department_code']
        labels = {
            'last_name': 'Фамилия',
            'first_name': 'Имя', 
            'patronymic': 'Отчество',
            'department_code': 'Код подразделения',
        }
        help_texts = {
            'department_code': 'Формат: Группа-Подгруппа-Подподгруппа (например: 35-1-1). Добавьте "У" для прав просмотра',
        }
        widgets = {
            'last_name': forms.TextInput(attrs={'placeholder': 'Введите вашу фамилию'}),
            'first_name': forms.TextInput(attrs={'placeholder': 'Введите ваше имя'}),
            'patronymic': forms.TextInput(attrs={'placeholder': 'Введите ваше отчество'}),
            'department_code': forms.TextInput(attrs={'placeholder': 'Например: 35-1-1'}),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Устанавливаем начальные значения из объекта User
        if self.instance and self.instance.user:
            self.fields['username'].initial = self.instance.user.username
            self.fields['email'].initial = self.instance.user.email
            
            # Убедимся, что данные из User синхронизированы с профилем
            if not self.instance.first_name and self.instance.user.first_name:
                self.instance.first_name = self.instance.user.first_name
            if not self.instance.last_name and self.instance.user.last_name:
                self.instance.last_name = self.instance.user.last_name
    
    def save(self, commit=True):
        profile = super().save(commit=False)
        
        # Обновляем связанного пользователя
        if profile.user:
            profile.user.username = self.cleaned_data['username']
            profile.user.email = self.cleaned_data['email']
            if commit:
                profile.user.save()
        
        if commit:
            profile.save()
            
        return profile

class UserEditForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ['first_name', 'last_name', 'email']
        labels = {
            'first_name': 'Имя',
            'last_name': 'Фамилия',
            'email': 'Email',
        }

# Остальные формы без изменений...
class TestSelectionForm(forms.Form):
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