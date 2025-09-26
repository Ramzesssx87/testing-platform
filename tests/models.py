from django.db import models
from django.contrib.auth.models import User
import json
from django.utils import timezone
import re

class Test(models.Model):
    name = models.CharField(max_length=255, verbose_name="Название теста")
    description = models.TextField(blank=True, verbose_name="Описание теста")
    created_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return self.name

class Question(models.Model):
    test = models.ForeignKey(Test, on_delete=models.CASCADE, related_name='questions')
    question_number = models.IntegerField(verbose_name="Номер вопроса")
    question_text = models.TextField(verbose_name="Текст вопроса")
    correct_answer = models.CharField(max_length=50, verbose_name="Правильные ответы")
    document_reference = models.CharField(max_length=255, verbose_name="Ссылка на документ")
    answer_options = models.JSONField(verbose_name="Варианты ответов")
    
    class Meta:
        ordering = ['question_number']
    
    def __str__(self):
        return f"Вопрос {self.question_number}: {self.question_text[:50]}..."

class UserProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    
    # Добавляем поля для ФИО
    last_name = models.CharField(
        max_length=100, 
        blank=True, 
        verbose_name="Фамилия",
        help_text="Введите вашу фамилию"
    )
    first_name = models.CharField(
        max_length=100, 
        blank=True, 
        verbose_name="Имя",
        help_text="Введите ваше имя"
    )
    patronymic = models.CharField(
        max_length=100, 
        blank=True, 
        verbose_name="Отчество",
        help_text="Введите ваше отчество"
    )
    
    department_code = models.CharField(
        max_length=50, 
        blank=True, 
        null=True,
        verbose_name="Код подразделения",
        help_text="Формат: Группа-Подгруппа-Подподгруппа (например: 35-1-1). Добавьте 'У' для прав просмотра"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return f"Профиль {self.user.username}"
    
    def get_full_name(self):
        """Возвращает полное ФИО пользователя"""
        parts = [self.last_name, self.first_name, self.patronymic]
        return ' '.join([part for part in parts if part]).strip()
    
    def get_short_name(self):
        """Возвращает краткое ФИО (Фамилия И.О.)"""
        if not self.last_name or not self.first_name:
            return self.user.username
            
        first_initial = self.first_name[0] + '.' if self.first_name else ''
        patronymic_initial = self.patronymic[0] + '.' if self.patronymic else ''
        
        return f"{self.last_name} {first_initial}{patronymic_initial}".strip()
    
    def parse_department_code(self):
        """Парсит код подразделения и возвращает компоненты"""
        if not self.department_code:
            return None
            
        code = self.department_code.upper().strip()
        
        # Разбиваем код на компоненты
        parts = code.split('-')
        group = parts[0] if len(parts) > 0 else None
        subgroup = parts[1] if len(parts) > 1 else None
        subsubgroup = parts[2] if len(parts) > 2 else None
        
        # Определяем уровень прав (убираем 'У' из последнего компонента)
        has_view_rights = False
        if group and 'У' in group:
            has_view_rights = True
            group = group.replace('У', '')
        elif subgroup and 'У' in subgroup:
            has_view_rights = True
            subgroup = subgroup.replace('У', '')
        elif subsubgroup and 'У' in subsubgroup:
            has_view_rights = True
            subsubgroup = subsubgroup.replace('У', '')
        
        return {
            'group': group,
            'subgroup': subgroup,
            'subsubgroup': subsubgroup,
            'has_view_rights': has_view_rights,
            'full_code': code
        }
    
    def can_view_other_results(self):
        """Проверяет, имеет ли пользователь права на просмотр чужих результатов"""
        parsed = self.parse_department_code()
        return parsed and parsed['has_view_rights']
    
    def get_viewable_users_query(self):
        """Возвращает QuerySet пользователей, чьи результаты может просматривать текущий пользователь"""
        from django.contrib.auth.models import User
        from django.db.models import Q
        
        parsed = self.parse_department_code()
        if not parsed or not parsed['has_view_rights']:
            return User.objects.none()
        
        # Базовый запрос
        query = Q(profile__department_code__isnull=False)
        
        # Определяем уровень доступа на основе структуры кода
        if parsed['subsubgroup']:  # Формат: 35-1-1У
            # Может видеть всех в своей подподгруппе
            pattern = f"{parsed['group']}-{parsed['subgroup']}-{parsed['subsubgroup']}%"
            query &= Q(profile__department_code__iregex=rf'^{parsed["group"]}-{parsed["subgroup"]}-{parsed["subsubgroup"]}[\wУ]*$')
        
        elif parsed['subgroup']:  # Формат: 35-1У
            # Может видеть всех в своей подгруппе (включая подподгруппы)
            query &= Q(profile__department_code__iregex=rf'^{parsed["group"]}-{parsed["subgroup"]}[\w-]*$')
        
        elif parsed['group']:  # Формат: 35У
            # Может видеть всех в своей группе
            query &= Q(profile__department_code__iregex=rf'^{parsed["group"]}[\w-]*$')
        
        # Исключаем самого себя из результатов
        return User.objects.filter(query).exclude(id=self.user.id)
    
    def get_department_hierarchy(self):
        """Возвращает иерархию подразделения пользователя"""
        parsed = self.parse_department_code()
        if not parsed:
            return "Не указано"
        
        hierarchy = []
        if parsed['group']:
            hierarchy.append(f"Группа {parsed['group']}")
        if parsed['subgroup']:
            hierarchy.append(f"Подгруппа {parsed['subgroup']}")
        if parsed['subsubgroup']:
            hierarchy.append(f"Подподгруппа {parsed['subsubgroup']}")
        
        return " → ".join(hierarchy)
    
    class Meta:
        verbose_name = "Профиль пользователя"
        verbose_name_plural = "Профили пользователей"

class UserTestProgress(models.Model):
    TEST_TYPES = [
        ('normal', 'Обычный тест'),
        ('express', 'Экспресс-тест'),
    ]
    
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    test = models.ForeignKey(Test, on_delete=models.CASCADE)
    test_type = models.CharField(max_length=10, choices=TEST_TYPES, default='normal')
    current_question = models.ForeignKey(Question, on_delete=models.SET_NULL, null=True, blank=True)
    completed = models.BooleanField(default=False)
    answers = models.JSONField(default=dict)
    start_question = models.IntegerField(null=True, blank=True, verbose_name="Начальный вопрос")
    end_question = models.IntegerField(null=True, blank=True, verbose_name="Конечный вопрос")
    time_limit_minutes = models.IntegerField(default=0, verbose_name="Лимит времени (минуты)")
    start_time = models.DateTimeField(null=True, blank=True, verbose_name="Время начала теста")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    # Новые поля для статистики
    score = models.FloatField(null=True, blank=True, verbose_name="Результат в процентах")
    correct_answers_count = models.IntegerField(null=True, blank=True, verbose_name="Количество правильных ответов")
    total_questions_count = models.IntegerField(null=True, blank=True, verbose_name="Общее количество вопросов")
    completed_at = models.DateTimeField(null=True, blank=True, verbose_name="Время завершения теста")
    
    # Уникальный идентификатор попытки
    attempt_id = models.CharField(max_length=100, unique=True, blank=True, null=True)
    
    class Meta:
        # Убираем unique_together, чтобы разрешить несколько попыток для одного теста
        ordering = ['-created_at']
    
    def __str__(self):
        type_str = "Экспресс" if self.test_type == 'express' else "Обычный"
        status = "Завершено" if self.completed else "В процессе"
        return f"{self.user.username} - {self.test.name} - {type_str} - {status} - {self.created_at.strftime('%d.%m.%Y %H:%M')}"
    
    def save(self, *args, **kwargs):
        # Генерируем уникальный attempt_id при создании
        if not self.attempt_id:
            timestamp = timezone.now().strftime("%Y%m%d%H%M%S")
            self.attempt_id = f"{self.user.id}_{self.test.id}_{timestamp}"
        
        # При завершении теста вычисляем результат
        if self.completed and not self.completed_at:
            self.completed_at = timezone.now()
            self.calculate_score()
        super().save(*args, **kwargs)
    
    def calculate_score(self):
        """Вычисляет результат теста"""
        if not self.answers:
            self.score = 0
            self.correct_answers_count = 0
            self.total_questions_count = 0
            return
        
        # Получаем вопросы теста с учетом диапазона
        questions_query = self.test.questions.all()
        
        if self.start_question:
            questions_query = questions_query.filter(question_number__gte=self.start_question)
        
        if self.end_question:
            questions_query = questions_query.filter(question_number__lte=self.end_question)
        
        questions = list(questions_query)
        self.total_questions_count = len(questions)
        
        # Считаем правильные ответы
        correct_count = 0
        for question in questions:
            user_answer = self.answers.get(str(question.id), [])
            correct_answers = [int(ans.strip()) for ans in question.correct_answer.split(',')]
            if set(user_answer) == set(correct_answers):
                correct_count += 1
        
        self.correct_answers_count = correct_count
        self.score = (correct_count / self.total_questions_count) * 100 if self.total_questions_count > 0 else 0
# Сигналы для автоматического создания профиля при создании пользователя
from django.db.models.signals import post_save
from django.dispatch import receiver

@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):
    if created:
        UserProfile.objects.create(user=instance)

@receiver(post_save, sender=User)
def save_user_profile(sender, instance, **kwargs):
    if hasattr(instance, 'profile'):
        instance.profile.save()
    else:
        UserProfile.objects.create(user=instance)