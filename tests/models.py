from django.db import models
from django.contrib.auth.models import User
import json

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
    correct_answer = models.CharField(max_length=50, verbose_name="Правильные ответы")  # Изменено на CharField
    document_reference = models.CharField(max_length=255, verbose_name="Ссылка на документ")
    answer_options = models.JSONField(verbose_name="Варианты ответов")  # храним как JSON
    
    class Meta:
        ordering = ['question_number']
    
    def __str__(self):
        return f"Вопрос {self.question_number}: {self.question_text[:50]}..."

class UserTestProgress(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    test = models.ForeignKey(Test, on_delete=models.CASCADE)
    current_question = models.ForeignKey(Question, on_delete=models.SET_NULL, null=True, blank=True)
    completed = models.BooleanField(default=False)
    answers = models.JSONField(default=dict)
    start_question = models.IntegerField(null=True, blank=True, verbose_name="Начальный вопрос")
    end_question = models.IntegerField(null=True, blank=True, verbose_name="Конечный вопрос")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        unique_together = ('user', 'test')
    
    def __str__(self):
        return f"{self.user.username} - {self.test.name} - {'Завершено' if self.completed else 'В процессе'}"