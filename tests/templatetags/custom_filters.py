# tests/templatetags/custom_filters.py
from django import template
from django.utils import timezone
from datetime import timedelta

register = template.Library()

@register.filter
def get_quiz_urgency_class(quiz):
    """Определяет класс срочности для зачета"""
    now = timezone.now()
    if quiz.ends_at < now:
        return 'quiz-expired'
    
    time_left = quiz.ends_at - now
    
    # Меньше 24 часов
    if time_left < timedelta(hours=24):
        return 'quiz-urgent'
    # Меньше 72 часов (3 суток)
    elif time_left < timedelta(hours=72):
        return 'quiz-warning'
    # Больше 3 суток
    else:
        return 'quiz-normal'

@register.filter
def get_days_left(quiz):
    """Возвращает количество полных дней до окончания зачета"""
    now = timezone.now()
    if quiz.ends_at < now:
        return 0
    
    time_left = quiz.ends_at - now
    return time_left.days

# существующие фильтры...
@register.filter
def split(value, arg):
    return value.split(arg)

@register.filter
def get_item(dictionary, key):
    if dictionary is None:
        return None
    return dictionary.get(str(key))

@register.filter
def format_duration(seconds):
    try:
        seconds = int(seconds)
        minutes = seconds // 60
        seconds = seconds % 60
        return f"{minutes:02d}:{seconds:02d}"
    except (ValueError, TypeError):
        return "00:00"

@register.filter
def filter_test_type(attempts, test_type):
    if not attempts:
        return []
    return [attempt for attempt in attempts if attempt.test_type == test_type]

@register.filter
def first_by_score(attempts):
    if not attempts:
        return None
    return max(attempts, key=lambda x: x.score if x.score else 0)