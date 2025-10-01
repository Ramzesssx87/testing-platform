from django.db import models
from django.contrib.auth.models import User
from django.db.models.signals import post_save
from django.dispatch import receiver
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
        
        # Убираем все 'У' из кода для анализа структуры
        clean_code = code.replace('У', '')
        
        # Разбиваем код на компоненты
        parts = clean_code.split('-')
        group = parts[0] if len(parts) > 0 and parts[0] else None
        subgroup = parts[1] if len(parts) > 1 and parts[1] else None
        subsubgroup = parts[2] if len(parts) > 2 and parts[2] else None
        
        # Определяем уровень прав (проверяем наличие 'У' в оригинальном коде)
        has_view_rights = 'У' in code
        
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
            base_pattern = f"{parsed['group']}-{parsed['subgroup']}-{parsed['subsubgroup']}"
            query &= Q(profile__department_code__iregex=rf'^{base_pattern}[\wУ]*$')
        
        elif parsed['subgroup']:  # Формат: 35-1У
            # Может видеть всех в своей подгруппе (включая подподгруппы)
            base_pattern = f"{parsed['group']}-{parsed['subgroup']}"
            query &= Q(profile__department_code__iregex=rf'^{base_pattern}(?:$|-\w+[\wУ]*$)')
        
        elif parsed['group']:  # Формат: 35У
            # Может видеть всех в своей группе
            base_pattern = f"{parsed['group']}"
            query &= Q(profile__department_code__iregex=rf'^{base_pattern}(?:$|-\w+(?:$|-\w+[\wУ]*$))')
        
        # НЕ исключаем самого себя из результатов - пользователь должен видеть свои результаты
        return User.objects.filter(query)
    
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
    end_time = models.DateTimeField(null=True, blank=True, verbose_name="Время окончания теста")
    # Новые поля для статистики
    score = models.FloatField(null=True, blank=True, verbose_name="Результат в процентах")
    correct_answers_count = models.IntegerField(null=True, blank=True, verbose_name="Количество правильных ответов")
    total_questions_count = models.IntegerField(null=True, blank=True, verbose_name="Общее количество вопросов")
    completed_at = models.DateTimeField(null=True, blank=True, verbose_name="Время завершения теста")
    
     # Новое поле для хранения порядка вопросов в экспресс-тесте
    question_order = models.JSONField(
        null=True, 
        blank=True, 
        verbose_name="Порядок вопросов в экспресс-тесте"
    )

    # Добавьте связь с QuizSession
    quiz_session = models.ForeignKey(
        'QuizSession', 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        related_name='progress_records'
    )

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
        
    # Время теста
    def is_time_expired(self):
        """Проверяет, истекло ли время теста"""
        if not self.end_time:
            return False
        return timezone.now() > self.end_time

    def get_remaining_time(self):
        """Возвращает оставшееся время в секундах"""
        if not self.end_time:
            return None
        now = timezone.now()
        if now > self.end_time:
            return 0
        return (self.end_time - now).total_seconds()

# Сигналы для автоматического создания профиля при создании пользователя
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

# Функция для проведения зачета по тестам

class QuizSession(models.Model):
    """Сессия зачета для группы"""
    creator = models.ForeignKey(User, on_delete=models.CASCADE, related_name='created_quizzes')
    test = models.ForeignKey(Test, on_delete=models.CASCADE)
    question_count = models.IntegerField(default=20, verbose_name="Количество вопросов")
    time_limit_minutes = models.IntegerField(default=45, verbose_name="Лимит времени (минуты)")
    created_at = models.DateTimeField(auto_now_add=True)
    starts_at = models.DateTimeField(verbose_name="Время начала зачета")
    ends_at = models.DateTimeField(verbose_name="Время окончания зачета")
    is_active = models.BooleanField(default=False, verbose_name="Активен")
    # Новое поле для отслеживания принудительной активации
    manually_activated = models.BooleanField(default=False, verbose_name="Активирован вручную")
    
    # Поля для хранения информации о вопросах
    question_order = models.JSONField(verbose_name="Порядок вопросов")
    
    def is_available_for_user(self, user):
        """Проверяет, доступен ли зачет для пользователя"""
        if not self.is_active:
            return False
        
        now = timezone.now()
        if now > self.ends_at:
            return False
            
        # Проверяем, является ли пользователь участником
        return self.participants.filter(user=user).exists()
    
    def get_user_participant(self, user):
        """Возвращает участника для пользователя"""
        try:
            return self.participants.get(user=user)
        except QuizParticipant.DoesNotExist:
            return None
    
    class Meta:
        ordering = ['-created_at']
        verbose_name = "Сессия зачета"
        verbose_name_plural = "Сессии зачетов"
    
    def __str__(self):
        return f"Зачет {self.test.name} от {self.creator.username}"
    
    def check_activation(self):
        """Проверяет и обновляет статус активации зачета"""
        now = timezone.now()
        
        # Если зачет уже активирован, ничего не делаем
        if self.is_active:
            return True
            
        # Если время начала наступило, активируем автоматически
        if now >= self.starts_at:
            self.is_active = True
            self.save()
            return True
            
        return False
    
    def activate_manually(self):
        """Принудительная активация зачета"""
        self.is_active = True
        self.manually_activated = True
        self.save()

class QuizParticipant(models.Model):
    """Участник зачета"""
    quiz_session = models.ForeignKey(QuizSession, on_delete=models.CASCADE, related_name='participants')
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    progress = models.OneToOneField(UserTestProgress, on_delete=models.CASCADE, null=True, blank=True)
    joined_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        unique_together = ['quiz_session', 'user']
        verbose_name = "Участник зачета"
        verbose_name_plural = "Участники зачетов"
    
    def __str__(self):
        return f"{self.user.username} - {self.quiz_session}"
    
    def update_completion_status(self):
        """Обновляет статус завершения на основе прогресса теста"""
        if self.progress and self.progress.completed and not self.completed_at:
            self.completed_at = self.progress.completed_at
            self.save()