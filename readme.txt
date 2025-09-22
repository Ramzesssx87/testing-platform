markdown
# Платформа тестирования

Django-приложение для создания и прохождения тестов.

## Установка

1. Клонируйте репозиторий
2. Создайте виртуальное окружение: `python -m venv venv`
3. Активируйте окружение: `venv\Scripts\activate` (Windows)
4. Установите зависимости: `pip install -r requirements.txt`
5. Скопируйте `.env.example` в `.env` и настройте переменные окружения
6. Выполните миграции: `python manage.py migrate`
7. Запустите сервер: `python manage.py runserver`
