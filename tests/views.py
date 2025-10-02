import json
import tempfile
import os
import random
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login, authenticate, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth.models import User
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from django.contrib import messages
from django.db.models import Count, Avg  # Добавляем Avg здесь
from django.utils import timezone
from .models import UserProfile, Test, Question, UserTestProgress, QuizSession, QuizParticipant
from .forms import TestSelectionForm, CustomUserCreationForm, ExcelUploadForm, ExpressTestForm
from .forms import UserEditForm, UserProfileForm, QuizCreationForm
from django.utils.safestring import mark_safe
from django.http import HttpResponse
from openpyxl import Workbook
from django.views.decorators.http import require_GET
from django.db.models import Count, Avg, Min, Max
from datetime import datetime, timedelta
from collections import defaultdict


def register_view(request):
    if request.method == 'POST':
        form = CustomUserCreationForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            
            # ПРИНУДИТЕЛЬНО ОБНОВЛЯЕМ ДАННЫЕ ИЗ БАЗЫ
            user.refresh_from_db()
            if hasattr(user, 'profile'):
                user.profile.refresh_from_db()
            
            # УЛУЧШЕННАЯ СИНХРОНИЗАЦИЯ ЗАЧЕТОВ ПРИ РЕГИСТРАЦИИ
            from .models import QuizSession, QuizParticipant
            from django.utils import timezone
            
            now = timezone.now()
            user_profile = user.profile
            
            #print(f"=== ДЕТАЛЬНАЯ СИНХРОНИЗАЦИЯ ЗАЧЕТОВ ДЛЯ {user.username} ===")
            #print(f"Код подразделения пользователя: {user_profile.department_code}")

            if user_profile.department_code:
                try:
                    user_code = user_profile.department_code.upper().strip()
                    #print(f"Код пользователя для синхронизации: {user_code}")
                    
                    # Разбираем код пользователя на уровни иерархии (БЕЗ У)
                    user_parts = user_code.replace('У', '').split('-')
                    user_levels = []
                    for i in range(len(user_parts)):
                        level_code = '-'.join(user_parts[:i+1])
                        user_levels.append(level_code)
                    #print(f"Уровни иерархии пользователя (без У): {user_levels}")

                    # Ищем активные зачеты
                    active_quizzes = QuizSession.objects.filter(
                        ends_at__gte=now,
                        is_active=True
                    ).select_related('creator', 'test').prefetch_related('participants')

                    #print(f"Найдено активных зачетов: {active_quizzes.count()}")

                    # Проверяем каждый зачет на принадлежность к иерархии пользователя
                    matching_quizzes = []
                    for quiz in active_quizzes:
                        creator_username = quiz.creator.username
                        creator_code = quiz.creator.profile.department_code if hasattr(quiz.creator, 'profile') else "Нет профиля"
                        
                        #print(f"\n--- Зачет: {quiz.test.name} ---")
                        #print(f"Создатель: {creator_username}")
                        #print(f"Код создателя: {creator_code}")
                        
                        # Проверяем, находится ли создатель зачета в иерархии пользователя
                        creator_in_user_hierarchy = False
                        if creator_code:
                            creator_code_clean = creator_code.upper().strip().replace('У', '')
                            creator_parts = creator_code_clean.split('-')
                            
                            # Создаем уровни иерархии создателя (БЕЗ У)
                            creator_levels = []
                            for i in range(len(creator_parts)):
                                level_code = '-'.join(creator_parts[:i+1])
                                creator_levels.append(level_code)
                            
                            # Проверяем пересечение уровней иерархии (БЕЗ У)
                            common_levels = set(user_levels) & set(creator_levels)
                            creator_in_user_hierarchy = bool(common_levels)
                            
                            #print(f"Уровни создателя (без У): {creator_levels}")
                            #print(f"Общие уровни: {common_levels}")
                            #print(f"Создатель в иерархии пользователя: {creator_in_user_hierarchy}")

                        #if creator_in_user_hierarchy:
                            #matching_quizzes.append(quiz)
                            #print("✓ ДОБАВЛЯЕМ: Создатель находится в иерархии пользователя")
                        #else:
                            #print("✗ ПРОПУСКАЕМ: Создатель не в иерархии пользователя")

                    # Добавляем пользователя в найденные зачеты
                    added_count = 0
                    for quiz in matching_quizzes:
                        # Проверяем, не добавлен ли уже
                        already_participant = QuizParticipant.objects.filter(
                            quiz_session=quiz, 
                            user=user
                        ).exists()
                        
                        if not already_participant:
                            QuizParticipant.objects.create(
                                quiz_session=quiz,
                                user=user
                            )
                            added_count += 1
                            print(f"✓ ПОЛЬЗОВАТЕЛЬ ДОБАВЛЕН В ЗАЧЕТ: {quiz.test.name}")
                        else:
                            print(f"ℹ ПОЛЬЗОВАТЕЛЬ УЖЕ УЧАСТНИК: {quiz.test.name}")

                    #print(f"\n=== ИТОГ ===")
                    #print(f"Добавлено зачетов: {added_count}")

                    if added_count > 0:
                        messages.info(request, f'Вы автоматически добавлены в {added_count} активных зачетов вашей группы.')
                    else:
                        messages.info(request, 'На данный момент нет активных зачетов в вашей группе.')
                        
                except Exception as e:
                    print(f"Ошибка при добавлении в зачеты при регистрации: {e}")
                    import traceback
                    traceback.print_exc()
            else:
                print("Код подразделения не указан - пропускаем синхронизацию зачетов")
                messages.info(request, 'Укажите код подразделения в профиле для доступа к зачетам вашей группы.')
            
            messages.success(request, f'Добро пожаловать, {user.username}! Регистрация прошла успешно.')
            return redirect('test_selection')
        else:
            messages.error(request, 'Пожалуйста, исправьте ошибки в форме.')
            return render(request, 'registration/register.html', {'form': form})
    else:
        form = CustomUserCreationForm()
        return render(request, 'registration/register.html', {'form': form})

    
def login_view(request):
    if request.method == 'POST':
        form = AuthenticationForm(request, data=request.POST)
        if form.is_valid():
            username = form.cleaned_data.get('username')
            password = form.cleaned_data.get('password')
            user = authenticate(username=username, password=password)
            if user is not None:
                login(request, user)
                return redirect('test_selection')
    else:
        form = AuthenticationForm()
    return render(request, 'registration/login.html', {'form': form})

def logout_view(request):
    logout(request)
    return redirect('login')

@login_required
def test_selection(request):
    # АВТОМАТИЧЕСКАЯ СИНХРОНИЗАЦИЯ ЗАЧЕТОВ ПРИ КАЖДОМ ЗАХОДЕ
    from .models import QuizSession, QuizParticipant
    from django.utils import timezone
    
    user = request.user
    user_profile = user.profile
    
    now = timezone.now()
    
    if user_profile.department_code:
        try:
            # Находим зачеты, созданные руководителями из той же группы
            group_users = user_profile.get_group_users()
            
            # Ищем активные зачеты, где создатель входит в ту же группу
            active_quizzes = QuizSession.objects.filter(
                ends_at__gte=now,
                is_active=True
            )
            
            # Фильтруем зачеты, где создатель в той же группе что и пользователь
            matching_quizzes = []
            for quiz in active_quizzes:
                if quiz.creator in group_users:
                    matching_quizzes.append(quiz)
            
            # Добавляем пользователя в найденные зачеты
            added_count = 0
            for quiz in matching_quizzes:
                if not QuizParticipant.objects.filter(
                    quiz_session=quiz, 
                    user=user
                ).exists():
                    QuizParticipant.objects.create(
                        quiz_session=quiz,
                        user=user
                    )
                    added_count += 1
            
            # Сообщение показываем только если добавлены новые зачеты
            # и это не первый запрос (чтобы избежать дублирования сообщений)
            if added_count > 0 and not request.session.get('synced_quizzes', False):
                messages.info(request, f'Доступно {added_count} новых зачетов вашей группы.')
                request.session['synced_quizzes'] = True
                
        except Exception as e:
            print(f"Ошибка при синхронизации зачетов: {e}")
    

    normal_form = TestSelectionForm()
    express_form = ExpressTestForm()
    
    # Получаем НЕЗАВЕРШЕННЫЕ доступные зачеты для пользователя
    available_quizzes = QuizSession.objects.filter(
        participants__user=request.user,
        ends_at__gte=timezone.now()  # Только те, что еще не закончились
    ).select_related('test').prefetch_related(
        'participants',
        'participants__progress'
    ).order_by('ends_at')  # Сортируем по времени окончания (ближайшие первые)
    
    # Фильтруем только те зачеты, которые пользователь еще НЕ завершил
    filtered_quizzes = []
    for quiz in available_quizzes:
        quiz.check_activation()  # Обновляем статус активации
        
        # Проверяем, завершил ли пользователь этот зачет
        user_participant = quiz.participants.filter(user=request.user).first()
        if user_participant and user_participant.progress and user_participant.progress.completed:
            continue  # Пропускаем завершенные зачеты
        
        filtered_quizzes.append(quiz)
    
    if request.method == 'POST':
        # Определяем, какая форма была отправлена
        if 'normal_test' in request.POST:
            form = TestSelectionForm(request.POST)
            if form.is_valid():
                test = form.cleaned_data['test']
                start_question = form.cleaned_data['start_question']
                end_question = form.cleaned_data['end_question']
                
                # Валидация диапазона вопросов
                if start_question and end_question and start_question > end_question:
                    form.add_error(None, "Начальный вопрос не может быть больше конечного")
                    return render(request, 'tests/test_selection.html', {
                        'normal_form': form,
                        'express_form': express_form
                    })
                
                # Получаем вопросы в выбранном диапазоне
                questions_query = test.questions.all()
                
                if start_question:
                    questions_query = questions_query.filter(question_number__gte=start_question)
                
                if end_question:
                    questions_query = questions_query.filter(question_number__lte=end_question)
                
                questions = list(questions_query)
                
                if not questions:
                    form.add_error(None, "В выбранном диапазоне нет вопросов")
                    return render(request, 'tests/test_selection.html', {
                        'normal_form': form,
                        'express_form': express_form
                    })
                
                # Вместо update_or_create создаем новую запись
                progress = UserTestProgress.objects.create(
                    user=request.user,
                    test=test,
                    current_question=questions[0],
                    completed=False,
                    answers={},
                    start_question=start_question,
                    end_question=end_question,
                    test_type='normal'
                )
                
                # Сохраняем ID попытки в сессии
                request.session['current_attempt_id'] = progress.attempt_id
                request.session['question_range'] = {
                    'start': start_question,
                    'end': end_question,
                    'question_ids': [q.id for q in questions],
                    'test_type': 'normal'
                }
                
                return redirect('test_progress', test_id=test.id)
        
        elif 'express_test' in request.POST:
            form = ExpressTestForm(request.POST)
            if form.is_valid():
                test = form.cleaned_data['test']
                question_count = form.cleaned_data['question_count']
                
                # Получаем все вопросы теста
                all_questions = list(test.questions.all())
                
                if not all_questions:
                    form.add_error(None, "В выбранном тесте нет вопросов")
                    return render(request, 'tests/test_selection.html', {
                        'normal_form': normal_form,
                        'express_form': form
                    })
                
                # Проверяем, что запрашиваемое количество не превышает доступное
                if question_count > len(all_questions):
                    question_count = len(all_questions)
                    messages.info(request, f"В тесте только {len(all_questions)} вопросов. Будет использовано максимальное количество.")
                
                # Выбираем случайные вопросы
                random_questions = random.sample(all_questions, question_count)
                
                # Сортируем по номеру вопроса для удобства
                random_questions.sort(key=lambda x: x.question_number)
                
                # Вместо update_or_create создаем новую запись
                progress = UserTestProgress.objects.create(
                    user=request.user,
                    test=test,
                    current_question=random_questions[0],
                    completed=False,
                    answers={},
                    start_question=1,
                    end_question=question_count,
                    test_type='express',
                    question_order=[q.id for q in random_questions]  # Сохраняем порядок вопросов
                )
                
                # Сохраняем ID попытки в сессии
                request.session['current_attempt_id'] = progress.attempt_id
                request.session['question_range'] = {
                    'start': 1,
                    'end': question_count,
                    'question_ids': [q.id for q in random_questions],
                    'test_type': 'express'
                }
                
                messages.success(request, f"Экспресс-тест начат! Случайно выбрано {question_count} вопросов.")
                return redirect('test_progress', test_id=test.id)
    
    # Получаем все активные (незавершенные) попытки
    active_progress = UserTestProgress.objects.filter(
        user=request.user,
        completed=False
    ).select_related('test').order_by('-created_at')
    
    # Создаем список для хранения информации о прогрессе
    progress_info = []
    for progress in active_progress:
        # Получаем вопросы в диапазоне для этого теста
        questions_query = progress.test.questions.all()
        
        if progress.start_question:
            questions_query = questions_query.filter(question_number__gte=progress.start_question)
        
        if progress.end_question:
            questions_query = questions_query.filter(question_number__lte=progress.end_question)
        
        questions_in_range = list(questions_query)
        total_in_range = len(questions_in_range)
        
        # Считаем количество отвеченных вопросов в диапазоне
        answered_in_range = 0
        for question in questions_in_range:
            if str(question.id) in progress.answers:
                answered_in_range += 1
        
        progress_info.append({
            'progress': progress,
            'total_in_range': total_in_range,
            'answered_in_range': answered_in_range
        })
    
    return render(request, 'tests/test_selection.html', {
        'normal_form': normal_form,
        'express_form': express_form,
        'progress_info': progress_info,
        'available_quizzes': filtered_quizzes
    })
    
@login_required
def test_progress(request, test_id):
    test = get_object_or_404(Test, id=test_id)
    
    # Получаем текущую попытку из сессии
    attempt_id = request.session.get('current_attempt_id')
    if not attempt_id:
        messages.error(request, 'Сессия теста не найдена. Пожалуйста, начните тест заново.')
        return redirect('test_selection')
    
    try:
        progress = UserTestProgress.objects.get(attempt_id=attempt_id, user=request.user, test=test)
    except UserTestProgress.DoesNotExist:
        messages.error(request, 'Прогресс теста не найден. Пожалуйста, начните тест заново.')
        return redirect('test_selection')
    
    # Проверяем, является ли это зачетом
    is_quiz = progress.test_type == 'quiz'

    # СЕРВЕРНАЯ ПРОВЕРКА ВРЕМЕНИ - ВАЖНО!
    if is_quiz and progress.end_time:
        if progress.is_time_expired():
            progress.completed = True
            progress.save()
            messages.error(request, 'Время зачета истекло!')
            return redirect('test_results', test_id=test_id)
    
    # Проверяем время для зачета
    if is_quiz and progress.end_time:
        now = timezone.now()
        if now > progress.end_time:
            progress.completed = True
            progress.save()
            messages.error(request, 'Время зачета истекло!')
            return redirect('test_results', test_id=test_id)
    
    # Получаем сохраненный диапазон вопросов из сессии
    question_range = request.session.get('question_range', {})
    question_ids = question_range.get('question_ids', [])
    test_type = question_range.get('test_type', 'normal')
    
    if question_ids:
        # Используем вопросы из диапазона
        questions = Question.objects.filter(id__in=question_ids).order_by('question_number')
        total_questions = len(question_ids)
    else:
        # Используем все вопросы
        questions = test.questions.all()
        total_questions = test.questions.count()
    
    # Если тест завершен, но пользователь хочет начать заново, сбрасываем прогресс
    if progress.completed and 'restart' not in request.GET:
        return redirect('test_results', test_id=test_id)
    
    current_question = progress.current_question

    # Находим порядковый номер вопроса в выбранном диапазоне
    if question_ids:
        question_list = list(questions)
        try:
            question_index = question_list.index(current_question) + 1
        except ValueError:
            # Если текущий вопрос не входит в диапазон, начинаем с первого
            progress.current_question = questions.first()
            progress.save()
            current_question = progress.current_question
            question_index = 1
        total_questions = len(question_list)
    else:
        question_index = current_question.question_number
        total_questions = test.questions.count()
    
    # Рассчитываем оставшееся время для зачета
    time_left = None
    if is_quiz and progress.end_time:
        now = timezone.now()
        time_left = (progress.end_time - now).total_seconds()
        # Если время отрицательное, устанавливаем 0
        if time_left < 0:
            time_left = 0
    
    # Логика обработки POST-запроса (ответ на вопрос)
    if request.method == 'POST':
        # Проверяем, была ли отправлена форма с ответами
        if 'answer' in request.POST:
            # Проверяем время для зачета перед обработкой ответа
            if is_quiz and progress.end_time and timezone.now() > progress.end_time:
                progress.completed = True
                progress.save()
                messages.error(request, 'Время зачета истекло!')
                return redirect('test_results', test_id=test_id)
            
            selected_answers = request.POST.getlist('answer')
            # Проверяем, что пользователь выбрал хотя бы один ответ
            if not selected_answers:
                messages.error(request, 'Пожалуйста, выберите хотя бы один ответ.')
                return redirect('test_progress', test_id=test_id)
            
            selected_answers = [int(answer) for answer in selected_answers]
            
            # Получаем правильные ответы
            correct_answers = [int(ans.strip()) for ans in current_question.correct_answer.split(',')]
            
            # Сохраняем ответ
            progress.answers[str(current_question.id)] = selected_answers
            progress.save()
            
            # Проверяем правильность ответа
            is_correct = set(selected_answers) == set(correct_answers)
            
            # Получаем следующий вопрос
            if question_ids:
                # Используем порядок вопросов из диапазона
                question_list = list(questions)
                current_index = question_list.index(current_question)
                if current_index + 1 < len(question_list):
                    next_question = question_list[current_index + 1]
                else:
                    next_question = None
            else:
                # Используем обычный порядок вопросов
                next_question = test.questions.filter(
                    question_number__gt=current_question.question_number
                ).first()
            
            # Если есть следующий вопрос, обновляем текущий вопрос в прогрессе
            if next_question:
                progress.current_question = next_question
                progress.save()

            # Рассчитываем оставшееся время для зачета
            time_left = None
            if is_quiz and progress.end_time:
                now = timezone.now()
                if now > progress.end_time:
                    time_left = 0
                    # Автоматически завершаем тест если время вышло
                    progress.completed = True
                    progress.save()
                    messages.error(request, 'Время зачета истекло!')
                    return redirect('test_results', test_id=test_id)
                else:
                    time_left = (progress.end_time - now).total_seconds()
            
            # Передаем текст вопроса в шаблон feedback
            return render(request, 'tests/answer_feedback.html', {
                'is_correct': is_correct,
                'correct_answers': correct_answers,
                'answer_options': current_question.answer_options,
                'document_reference': current_question.document_reference,
                'test': test,
                'next_question': next_question,
                'question_text': current_question.question_text,
                'is_quiz': is_quiz,
                'time_left': time_left,
                'question_number': question_index,
                'total_questions': total_questions,
                'progress': progress  # Добавляем эту строку
            })
        else:
            # Если форма отправлена без ответов (например, нажата кнопка "Пропустить")
            messages.warning(request, 'Вы не выбрали ответ на вопрос.')
    
    # Рендерим страницу с текущим вопросом
    return render(request, 'tests/test_progress.html', {
        'test': test,
        'question': current_question,
        'progress': progress,  # Убедитесь, что эта строка есть
        'question_number': question_index,
        'total_questions': total_questions,
        'test_type': test_type,
        'is_quiz': is_quiz,
        'time_left': time_left,
    })


@login_required
def test_results(request, test_id):

    test = get_object_or_404(Test, id=test_id)
    
    # Получаем attempt_id из GET-параметра
    attempt_id = request.GET.get('attempt_id')
    
    if not attempt_id:
        # Если attempt_id не передан, пытаемся найти из сессии
        attempt_id = request.session.get('current_attempt_id')
    
    if not attempt_id:
        messages.error(request, 'Идентификатор попытки не указан. Пожалуйста, перейдите к результатам через историю тестов.')
        return redirect('statistics')
    
    try:
        progress = UserTestProgress.objects.get(attempt_id=attempt_id, user=request.user, test=test)
    except UserTestProgress.DoesNotExist:
        messages.error(request, 'Результаты теста не найдены. Возможно, сессия устарела.')
        return redirect('statistics')
    
    # Получаем вопросы на основе типа теста
    if progress.test_type == 'express' or progress.test_type == 'quiz':
        # Для экспресс-теста и зачета используем сохраненный порядок вопросов
        question_range = request.session.get('question_range', {})
        question_ids = question_range.get('question_ids', [])
        
        if question_ids:
            # Получаем вопросы в том порядке, в котором они были в тесте
            questions = []
            for q_id in question_ids:
                try:
                    question = Question.objects.get(id=q_id, test=test)
                    questions.append(question)
                except Question.DoesNotExist:
                    continue
            total_questions = len(questions)
        else:
            # Если в сессии нет данных, используем сохраненный порядок из базы
            if progress.question_order:
                question_ids = progress.question_order
                questions = []
                for q_id in question_ids:
                    try:
                        question = Question.objects.get(id=q_id, test=test)
                        questions.append(question)
                    except Question.DoesNotExist:
                        continue
                total_questions = len(questions)
            else:
                # Если порядок не сохранен, используем вопросы по порядку номеров
                questions_query = test.questions.all()
                if progress.start_question:
                    questions_query = questions_query.filter(question_number__gte=progress.start_question)
                if progress.end_question:
                    questions_query = questions_query.filter(question_number__lte=progress.end_question)
                questions = list(questions_query.order_by('question_number'))
                total_questions = len(questions)
    else:
        # Для обычного теста используем реальный диапазон из прогресса
        questions_query = test.questions.all()
        if progress.start_question:
            questions_query = questions_query.filter(question_number__gte=progress.start_question)
        if progress.end_question:
            questions_query = questions_query.filter(question_number__lte=progress.end_question)
        questions = list(questions_query.order_by('question_number'))
        total_questions = len(questions)
    
    # Создаем список вопросов с их порядковыми номерами в тесте
    questions_with_order = []
    correct_answers = 0
    user_answers = {}
    
    for i, question in enumerate(questions, 1):
        user_answer = progress.answers.get(str(question.id), [])
        user_answers[str(question.id)] = user_answer
        
        # ПРАВИЛЬНОЕ ПРЕОБРАЗОВАНИЕ ПРАВИЛЬНЫХ ОТВЕТОВ
        correct_answers_list = []
        try:
            # Обрабатываем случай, когда correct_answer может быть пустым или содержать нечисловые значения
            if question.correct_answer:
                correct_parts = question.correct_answer.split(',')
                for part in correct_parts:
                    part = part.strip()
                    if part.isdigit():  # Проверяем, что часть является числом
                        correct_answers_list.append(int(part))
        except (ValueError, AttributeError):
            correct_answers_list = []
        
        # ПРАВИЛЬНАЯ ПРОВЕРКА СОВПАДЕНИЯ ОТВЕТОВ
        # Преобразуем user_answer в множество чисел для сравнения
        user_answer_set = set(int(ans) for ans in user_answer if str(ans).isdigit())
        correct_answers_set = set(correct_answers_list)
        
        is_correct = user_answer_set == correct_answers_set
        if is_correct:
            correct_answers += 1
        
        questions_with_order.append({
            'question': question,
            'order_number': i,
            'original_number': question.question_number,
            'correct_answers_list': correct_answers_list,
            'is_correct': is_correct
        })
    
    # ВЫЧИСЛЯЕМ РЕЗУЛЬТАТ ПОСЛЕ подсчета правильных ответов
    score = (correct_answers / total_questions) * 100 if total_questions > 0 else 0
    
    # Обновляем результат в прогресс теста (если еще не обновлено)
    if not progress.completed:
        progress.score = score  # Теперь переменная score определена
        progress.correct_answers_count = correct_answers
        progress.total_questions_count = total_questions
        progress.completed = True
        progress.completed_at = timezone.now()
        progress.save()
  
    # ОБНОВЛЯЕМ СТАТУС УЧАСТНИКА ЗАЧЕТА, если это зачет
    if progress.quiz_session:
        try:
            participant = QuizParticipant.objects.get(
                quiz_session=progress.quiz_session,
                user=request.user,
                progress=progress
            )
            # Используем метод update_completion_status если он есть, или напрямую обновляем
            if hasattr(participant, 'update_completion_status'):
                participant.update_completion_status()
            else:
                if participant.progress and participant.progress.completed and not participant.completed_at:
                    participant.completed_at = participant.progress.completed_at
                    participant.save()
        except QuizParticipant.DoesNotExist:
            pass  # Это не зачет или участник не найден
    
    return render(request, 'tests/test_results.html', {
        'test': test,
        'progress': progress,
        'correct_answers': correct_answers,
        'total_questions': total_questions,
        'score': score,
        'questions_with_order': questions_with_order,
        'user_answers': user_answers,
        'test_type': progress.test_type
    })

@login_required
@require_POST
@csrf_exempt
def save_answer(request):
    try:
        data = json.loads(request.body)
        question_id = data.get('question_id')
        answer = data.get('answer')
        
        question = get_object_or_404(Question, id=question_id)
        progress = get_object_or_404(
            UserTestProgress, 
            user=request.user, 
            test=question.test
        )
        
        progress.answers[str(question_id)] = answer
        progress.save()
        
        return JsonResponse({'status': 'success'})
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)})

# Добавьте эту функцию в конец файла views.py
@login_required
def reset_test_progress(request, test_id):
    test = get_object_or_404(Test, id=test_id)
    
    # Получаем попытку из GET-параметра или из сессии
    attempt_id = request.GET.get('attempt_id') or request.session.get('current_attempt_id')
    
    if attempt_id:
        try:
            progress = UserTestProgress.objects.get(attempt_id=attempt_id, user=request.user, test=test)
            
            # Получаем вопросы в выбранном диапазоне
            questions_query = test.questions.all()
            
            if progress.start_question:
                questions_query = questions_query.filter(question_number__gte=progress.start_question)
            
            if progress.end_question:
                questions_query = questions_query.filter(question_number__lte=progress.end_question)
            
            questions = list(questions_query)
            
            # Сбрасываем прогресс
            progress.current_question = questions[0] if questions else test.questions.first()
            progress.completed = False
            progress.answers = {}
            progress.score = None
            progress.correct_answers_count = None
            progress.total_questions_count = None
            progress.completed_at = None
            progress.save()
            
            # Обновляем сессию
            request.session['current_attempt_id'] = progress.attempt_id
            
        except UserTestProgress.DoesNotExist:
            messages.error(request, 'Прогресс теста не найден.')
    else:
        messages.error(request, 'Идентификатор попытки не указан.')
    
    # Перенаправляем на страницу выбора теста
    return redirect('test_selection')

@login_required
def upload_test_excel(request):
    if not request.user.is_staff:
        messages.error(request, 'У вас нет прав для загрузки тестов')
        return redirect('test_selection')
    
    if request.method == 'POST':
        form = ExcelUploadForm(request.POST, request.FILES)
        if form.is_valid():
            excel_file = request.FILES['excel_file']
            test_name = form.cleaned_data.get('test_name')
            
            # Проверяем расширение файла
            if not excel_file.name.endswith(('.xlsx', '.xls')):
                messages.error(request, 'Файл должен быть в формате Excel (.xlsx или .xls)')
                return render(request, 'tests/upload_excel.html', {'form': form})
            
            # Сохраняем файл временно
            with tempfile.NamedTemporaryFile(delete=False, suffix='.xlsx') as tmp_file:
                for chunk in excel_file.chunks():
                    tmp_file.write(chunk)
                tmp_file_name = tmp_file.name
            
            try:
                # Импортируем тест
                from .excel_importer import import_test_from_excel
                test = import_test_from_excel(tmp_file_name, test_name)
                messages.success(request, f'Тест {test.name} успешно импортирован! Создано {test.questions.count()} вопросов.')
            except Exception as e:
                messages.error(request, f'Ошибка при импорте теста: {str(e)}')
            finally:
                # Удаляем временный файл
                try:
                    os.unlink(tmp_file_name)
                except:
                    pass  # Игнорируем ошибки удаления временного файла
                
            return redirect('test_selection')
    else:
        form = ExcelUploadForm()
    
    return render(request, 'tests/upload_excel.html', {'form': form})

# tests/views.py - обновим функцию manage_tests
@login_required
def manage_tests(request):
    if not request.user.is_staff:
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({'status': 'error', 'message': 'У вас нет прав для управления тестами'})
        else:
            messages.error(request, 'У вас нет прав для управления тестами')
            return redirect('test_selection')
    
    tests = Test.objects.all().annotate(question_count=Count('questions'))
    
    if request.method == 'POST':
        test_id = request.POST.get('test_id')
        action = request.POST.get('action')
        
        if test_id and action == 'delete':
            test = get_object_or_404(Test, id=test_id)
            test_name = test.name
            test.delete()
            
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({'status': 'success', 'message': f'Тест {test_name} был успешно удален'})
            else:
                messages.success(request, f'Тест {test_name} был успешно удален')
                return redirect('manage_tests')
        
        elif test_id and action == 'edit':
            # Обработка редактирования теста
            test = get_object_or_404(Test, id=test_id)
            test_name = request.POST.get('test_name')
            test_description = request.POST.get('test_description')
            
            if test_name:
                test.name = test_name
            if test_description is not None:
                test.description = test_description
            
            test.save()
            
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({'status': 'success', 'message': 'Тест успешно обновлен'})
            else:
                messages.success(request, f'Тест {test.name} успешно обновлен')
                return redirect('manage_tests')
    
    # Для GET-запросов возвращаем HTML-страницу
    return render(request, 'tests/manage_tests.html', {'tests': tests})
# Добавим возможность экспорта тестов в Excel:
# tests/views.py - обновим функцию export_test_excel
@login_required
@require_GET
def export_test_excel(request, test_id):
    if not request.user.is_staff:
        messages.error(request, 'У вас нет прав для экспорта тестов')
        return redirect('test_selection')
    
    test = get_object_or_404(Test, id=test_id)
    
    # Создаем Excel файл
    wb = Workbook()
    ws = wb.active
    ws.title = test.name[:31]  # Ограничение длины названия листа в Excel
    
    # Заголовки не нужны для этого формата
    # Данные
    row_num = 1
    for question in test.questions.all().order_by('question_number'):
        # Добавляем номер вопроса и текст
        ws.append([question.question_number, question.question_text])
        
        # Добавляем варианты ответов каждый в отдельной строке
        for option_num, option_text in sorted(question.answer_options.items()):
            ws.append([None, f"{option_num}. {option_text}"])
        
        # Добавляем пустую строку между вопросами
        ws.append([None, None])
        row_num += len(question.answer_options) + 3
    
    # Создаем HTTP response
    response = HttpResponse(
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    response['Content-Disposition'] = f'attachment; filename="Тест_{test.name}.xlsx"'
    
    wb.save(response)
    return response

# tests/views.py - обновим функцию export_answers_excel
@login_required
@require_GET
def export_answers_excel(request, test_id):
    if not request.user.is_staff:
        messages.error(request, 'У вас нет прав для экспорта ответов')
        return redirect('test_selection')
    
    test = get_object_or_404(Test, id=test_id)
    
    # Создаем Excel файл
    wb = Workbook()
    ws = wb.active
    ws.title = "Ответы"[:31]  # Ограничение длины названия листа в Excel
    
    # Заголовки
    headers = ['Номер вопроса', 'Текст вопроса', 'Правильные ответы']
    ws.append(headers)
    
    # Данные
    for question in test.questions.all().order_by('question_number'):
        row = [
            question.question_number,
            question.question_text,
            question.correct_answer
        ]
        
        ws.append(row)
    
    # Создаем HTTP response
    response = HttpResponse(
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    response['Content-Disposition'] = f'attachment; filename="Ответы_{test.name}.xlsx"'
    
    wb.save(response)
    return response

@login_required
def profile(request):
    """Личный кабинет пользователя"""
    user = request.user
    profile = user.profile
    
    # Статистика пользователя
    completed_tests = UserTestProgress.objects.filter(
        user=user, 
        completed=True
    ).count()
    
    express_tests = UserTestProgress.objects.filter(
        user=user, 
        test_type='express',
        completed=True
    ).count()
    
    average_score = UserTestProgress.objects.filter(
        user=user, 
        completed=True,
        score__isnull=False
    ).aggregate(avg_score=Avg('score'))['avg_score'] or 0
    
    return render(request, 'profile.html', {
        'user': user,
        'profile': profile,
        'completed_tests': completed_tests,
        'express_tests': express_tests,
        'average_score': round(average_score, 1)
    })

@login_required
def edit_profile(request):
    """Редактирование профиля пользователя"""
    if request.method == 'POST':
        # Используем только UserProfileForm, которая теперь включает все необходимые поля
        profile_form = UserProfileForm(request.POST, instance=request.user.profile)
        
        if profile_form.is_valid():
            # Сохраняем данные профиля (включая username, email, ФИО)
            profile_form.save()
            
            messages.success(request, 'Ваш профиль успешно обновлен!')
            return redirect('profile')
        else:
            messages.error(request, 'Пожалуйста, исправьте ошибки в форме.')
    else:
        # Используем только одну форму
        profile_form = UserProfileForm(instance=request.user.profile)
    
    return render(request, 'edit_profile.html', {
        'profile_form': profile_form
    })

@login_required
def statistics(request):
    """Статистика тестов пользователя - теперь использует общую функцию"""
    return statistics_for_user(request, request.user, is_own_profile=True)

@login_required
@require_POST
def reset_statistics(request):
    """Сброс статистики пользователя (только тренировки и экспресс-тесты, зачеты не удаляются)"""
    # Удаляем только тренировки и экспресс-тесты, зачеты оставляем
    deleted_count = UserTestProgress.objects.filter(
        user=request.user,
        completed=True,
        test_type__in=['normal', 'express']  # Только обычные тесты и экспресс-тесты
    ).delete()[0]
    
    messages.success(request, f'Статистика сброшена. Удалено записей: {deleted_count}. Зачеты сохранены.')
    return redirect('statistics')

@login_required
def delete_test_progress(request, test_id):
    test = get_object_or_404(Test, id=test_id)
    
    # Получаем попытку из GET-параметра или из сессии
    attempt_id = request.GET.get('attempt_id') or request.POST.get('attempt_id') or request.session.get('current_attempt_id')
    
    if attempt_id:
        try:
            progress = UserTestProgress.objects.get(attempt_id=attempt_id, user=request.user, test=test)
            
            # ЗАПРЕЩАЕМ УДАЛЕНИЕ ЗАЧЕТОВ
            if progress.test_type == 'quiz':
                messages.error(request, 'Нельзя удалять результаты зачетов.')
                return redirect('test_selection')
            
            # Если удаляемая попытка является текущей в сессии, очищаем сессию
            if request.session.get('current_attempt_id') == attempt_id:
                if 'current_attempt_id' in request.session:
                    del request.session['current_attempt_id']
                if 'question_range' in request.session:
                    del request.session['question_range']
            
            # Удаляем прогресс (только для тренировок и экспресс-тестов)
            progress.delete()
            messages.success(request, f'Прогресс по тесту "{test.name}" был удален.')
            
        except UserTestProgress.DoesNotExist:
            messages.error(request, 'Прогресс теста не найден.')
    else:
        messages.error(request, 'Идентификатор попытки не указан.')
    
    return redirect('test_selection')


@login_required
def group_results(request):
    """Просмотр результатов тестов пользователей в группе - лучшие результаты по каждому тесту отдельно"""
    user_profile = request.user.profile
    
    # Проверяем права доступа
    if not user_profile.can_view_other_results():
        messages.error(request, 'У вас нет прав для просмотра результатов группы.')
        return redirect('profile')
    
    # Получаем пользователей, чьи результаты можно просматривать
    viewable_users = user_profile.get_viewable_users_query()
    
    # Базовый запрос для завершенных ЭКСПРЕСС-тестов
    completed_tests = UserTestProgress.objects.filter(
        user__in=viewable_users,
        completed=True,
        score__isnull=False,
        test_type='express'  # ТОЛЬКО экспресс-тесты
    ).select_related('user', 'test').order_by('-completed_at')
    
    # Базовый запрос для завершенных ЗАЧЕТОВ
    quiz_results = UserTestProgress.objects.filter(
        user__in=viewable_users,
        completed=True,
        score__isnull=False,
        test_type='quiz'  # ТОЛЬКО зачеты
    ).select_related('user', 'test', 'quiz_session').order_by('-completed_at')
    
    # Фильтрация по тесту, если указан
    test_filter = request.GET.get('test')
    if test_filter:
        completed_tests = completed_tests.filter(test_id=test_filter)
        quiz_results = quiz_results.filter(test_id=test_filter)  # ПРИМЕНЯЕМ ФИЛЬТР К ЗАЧЕТАМ
    
    # Фильтрация по дате
    date_from = request.GET.get('date_from')
    date_to = request.GET.get('date_to')
    if date_from:
        completed_tests = completed_tests.filter(completed_at__gte=date_from)
        quiz_results = quiz_results.filter(completed_at__gte=date_from)  # ПРИМЕНЯЕМ ФИЛЬТР К ЗАЧЕТАМ
    if date_to:
        completed_tests = completed_tests.filter(completed_at__lte=date_to)
        quiz_results = quiz_results.filter(completed_at__lte=date_to)  # ПРИМЕНЯЕМ ФИЛЬТР К ЗАЧЕТАМ
    
    # Собираем лучшие результаты для каждого пользователя и КАЖДОГО теста отдельно (ЭКСПРЕСС-ТЕСТЫ)
    best_results_dict = {}
    
    for test_progress in completed_tests:
        user_id = test_progress.user.id
        test_id = test_progress.test.id
        
        # Ключ: пользователь + тест (для каждого теста отдельно)
        key = f"{user_id}_{test_id}"
        
        # Если у пользователя еще нет результата по этому тесту или текущий результат лучше
        if key not in best_results_dict:
            best_results_dict[key] = test_progress
        else:
            # Сравниваем результаты - берем лучший
            existing_progress = best_results_dict[key]
            if test_progress.score > existing_progress.score:
                best_results_dict[key] = test_progress
    
    # Преобразуем словарь обратно в список
    best_results = list(best_results_dict.values())
    
    # Собираем лучшие результаты зачетов для каждого пользователя и КАЖДОГО теста отдельно
    best_quiz_results_dict = {}
    
    for quiz_progress in quiz_results:
        user_id = quiz_progress.user.id
        test_id = quiz_progress.test.id
        
        key = f"{user_id}_{test_id}"
        
        if key not in best_quiz_results_dict:
            best_quiz_results_dict[key] = quiz_progress
        else:
            existing_progress = best_quiz_results_dict[key]
            if quiz_progress.score > existing_progress.score:
                best_quiz_results_dict[key] = quiz_progress
    
    best_quiz_results = list(best_quiz_results_dict.values())
    
    # Сортируем по фамилии, названию теста и результату
    best_results.sort(key=lambda x: (x.user.profile.last_name or '', x.test.name, -x.score))
    best_quiz_results.sort(key=lambda x: (x.user.profile.last_name or '', x.test.name, -x.score))
    
    # Получаем список доступных тестов для фильтра (и экспресс-тесты и зачеты)
    available_tests_express = Test.objects.filter(
        usertestprogress__user__in=viewable_users,
        usertestprogress__completed=True,
        usertestprogress__test_type='express'
    ).distinct()
    
    available_tests_quiz = Test.objects.filter(
        usertestprogress__user__in=viewable_users,
        usertestprogress__completed=True,
        usertestprogress__test_type='quiz'
    ).distinct()
    
    # Объединяем тесты из обоих типов
    available_tests = available_tests_express.union(available_tests_quiz)
    
    # Получаем названия тестов для отображения в шаблоне
    test_names = {str(test.id): test.name for test in available_tests}
    
    # Статистика по группе
    total_users = viewable_users.count()
    
    # Считаем уникальные тесты и пользователей
    unique_express_tests = len(set((r.user.id, r.test.id) for r in best_results))
    unique_quiz_tests = len(set((r.user.id, r.test.id) for r in best_quiz_results))
    
    # Средний балл по группе (по всем результатам)
    if best_results:
        avg_score = sum(result.score for result in best_results) / len(best_results)
    else:
        avg_score = 0
    
    # Средний балл по зачетам
    if best_quiz_results:
        avg_quiz_score = sum(result.score for result in best_quiz_results) / len(best_quiz_results)
    else:
        avg_quiz_score = 0
    
    return render(request, 'tests/group_results.html', {
        'viewable_users': viewable_users,
        'completed_tests': best_results,
        'quiz_tests': best_quiz_results,
        'available_tests': available_tests,
        'test_names': test_names,
        'total_users': total_users,
        'total_tests': unique_express_tests,  # Количество уникальных комбинаций пользователь-тест
        'total_quiz_tests': unique_quiz_tests,
        'avg_score': round(avg_score, 1),
        'avg_quiz_score': round(avg_quiz_score, 1),
        'user_profile': user_profile,
    })

@login_required
def user_statistics_view(request, user_id):
    """Просмотр статистики конкретного пользователя (для руководителей)"""
    # Проверяем права доступа
    if not request.user.profile.can_view_other_results():
        messages.error(request, 'У вас нет прав для просмотра статистики других пользователей.')
        return redirect('profile')
    
    target_user = get_object_or_404(User, id=user_id)
    
    # Проверяем, что текущий пользователь имеет право просматривать статистику target_user
    viewable_users = request.user.profile.get_viewable_users_query()
    if target_user not in viewable_users:
        messages.error(request, 'У вас нет прав для просмотра статистики этого пользователя.')
        return redirect('group_results')
    
    # Используем существующую функцию statistics, но с другим пользователем
    return statistics_for_user(request, target_user, is_own_profile=False)

def statistics_for_user(request, target_user, is_own_profile=True):
    """Общая функция для отображения статистики (для своего профиля и для просмотра другими)"""
    # Автоматически удаляем тесты старше 2 месяцев (только для своего профиля, кроме зачетов)
    if is_own_profile:
        two_months_ago = timezone.now() - timezone.timedelta(days=60)
        old_tests = UserTestProgress.objects.filter(
            user=target_user,
            completed_at__lt=two_months_ago,
            test_type__in=['normal', 'express']  # Удаляем только тренировки и экспресс-тесты
        )
        old_tests_count = old_tests.count()
        old_tests.delete()
        
        if old_tests_count > 0:
            messages.info(request, f'Автоматически удалено {old_tests_count} записей тренировок и экспресс-тестов старше 2 месяцев. Зачеты сохранены.')
    
    # Получаем все завершенные тесты (только за последние 2 месяца)
    two_months_ago = timezone.now() - timezone.timedelta(days=60)
    all_completed_tests = UserTestProgress.objects.filter(
        user=target_user,
        completed=True,
        completed_at__gte=two_months_ago
    ).select_related('test').order_by('-completed_at')
    
    # Разделяем на тренировки и экспресс-тесты
    training_tests = all_completed_tests.filter(test_type='normal')
    
    # ДЛЯ ЭКСПРЕСС-ТЕСТОВ: получаем только лучший результат по каждому тесту
    express_tests_all = all_completed_tests.filter(test_type='express')
    
    # Собираем лучшие результаты по каждому тесту отдельно
    best_express_results = {}
    for test_progress in express_tests_all:
        test_id = test_progress.test.id
        if test_id not in best_express_results or test_progress.score > best_express_results[test_id].score:
            best_express_results[test_id] = test_progress
    
    express_tests = list(best_express_results.values())
    express_tests.sort(key=lambda x: x.completed_at, reverse=True)  # Сортируем по дате
    
    # ДОБАВЛЯЕМ РЕЗУЛЬТАТЫ ЗАЧЕТОВ
    quiz_tests_all = all_completed_tests.filter(test_type='quiz')
    
    # Собираем лучшие результаты зачетов по каждому тесту отдельно
    best_quiz_results = {}
    for quiz_progress in quiz_tests_all:
        test_id = quiz_progress.test.id
        if test_id not in best_quiz_results or quiz_progress.score > best_quiz_results[test_id].score:
            best_quiz_results[test_id] = quiz_progress
    
    quiz_tests = list(best_quiz_results.values())
    quiz_tests.sort(key=lambda x: x.completed_at, reverse=True)
    
    # ОБНОВЛЕННАЯ СТАТИСТИКА:
    total_trainings = training_tests.count()
    
    # ВМЕСТО количества лучших тестов - считаем общее количество пройденных тестов
    total_express_tests_all = express_tests_all.count()  # Все экспресс-тесты (включая повторные)
    total_quiz_tests_all = quiz_tests_all.count()        # Все зачеты (включая повторные)
    
    total_all_tests = total_trainings + total_express_tests_all + total_quiz_tests_all
    
    # Средний результат за последние 10 тренировок
    last_10_trainings = list(training_tests[:10])
    if last_10_trainings:
        training_scores = [test.score for test in last_10_trainings if test.score is not None]
        average_training_last_10 = sum(training_scores) / len(training_scores) if training_scores else 0
    else:
        average_training_last_10 = 0
    
    # Средний результат по всем экспресс-тестам (не только лучшим)
    if express_tests_all:
        express_scores = [test.score for test in express_tests_all if test.score is not None]
        average_express = sum(express_scores) / len(express_scores) if express_scores else 0
    else:
        average_express = 0
    
    # Средний результат по всем зачетам (не только лучшим)
    if quiz_tests_all:
        quiz_scores = [test.score for test in quiz_tests_all if test.score is not None]
        average_quiz = sum(quiz_scores) / len(quiz_scores) if quiz_scores else 0
    else:
        average_quiz = 0
    
    # Для таблиц - НЕ ограничиваем показ, показываем все лучшие результаты
    training_tests_limited = list(training_tests[:20])  # Ограничиваем только тренировки
    express_tests_limited = express_tests  # Все лучшие экспресс-тесты
    quiz_tests_limited = quiz_tests  # Все лучшие зачеты
    
    # Определяем, нужно ли показывать кнопки "Показать все"
    has_more_trainings = total_trainings > 20
    has_more_express = False  # Теперь показываем все лучшие результаты
    has_more_quiz = False     # Теперь показываем все лучшие результаты
    
    template_name = 'statistics.html' if is_own_profile else 'user_statistics_view.html'
    
    return render(request, template_name, {
        'target_user': target_user,
        'is_own_profile': is_own_profile,
        'total_trainings': total_trainings,
        'total_express_tests': total_express_tests_all,  # Теперь общее количество экспресс-тестов
        'total_quiz_tests': total_quiz_tests_all,        # Теперь общее количество зачетов
        'total_all_tests': total_all_tests,
        'average_training_last_10': round(average_training_last_10, 1),
        'average_express': round(average_express, 1),
        'average_quiz': round(average_quiz, 1),
        'training_tests': training_tests,
        'training_tests_limited': training_tests_limited,
        'express_tests': express_tests,
        'express_tests_limited': express_tests_limited,
        'quiz_tests': quiz_tests,
        'quiz_tests_limited': quiz_tests_limited,
        'has_more_trainings': has_more_trainings,
        'has_more_express': has_more_express,
        'has_more_quiz': has_more_quiz,
        'unique_express_tests': len(express_tests),  # Количество уникальных тестов с лучшими результатами
        'unique_quiz_tests': len(quiz_tests),        # Количество уникальных зачетов с лучшими результатами
    })


@login_required
def user_test_results(request, user_id, test_id):
    """Просмотр детальных результатов конкретного пользователя"""
    # Проверяем права доступа
    if not request.user.profile.can_view_other_results():
        messages.error(request, 'У вас нет прав для просмотра этих результатов.')
        return redirect('profile')
    
    target_user = get_object_or_404(User, id=user_id)
    test = get_object_or_404(Test, id=test_id)
    
    # Проверяем, что текущий пользователь имеет право просматривать результаты target_user
    viewable_users = request.user.profile.get_viewable_users_query()
    if target_user != request.user and target_user not in viewable_users:
        messages.error(request, 'У вас нет прав для просмотра результатов этого пользователя.')
        return redirect('group_results')
    
    # Получаем attempt_id из GET-параметра
    attempt_id = request.GET.get('attempt_id')
    
    if attempt_id:
        # Получаем конкретную попытку по attempt_id
        try:
            attempt = UserTestProgress.objects.get(
                attempt_id=attempt_id,
                user=target_user,
                test=test,
                completed=True
            )
        except UserTestProgress.DoesNotExist:
            messages.error(request, 'Указанная попытка теста не найдена.')
            return redirect('group_results')
    else:
        # Получаем последнюю завершенную попытку пользователя по этому тесту
        attempts = UserTestProgress.objects.filter(
            user=target_user,
            test=test,
            completed=True
        ).order_by('-completed_at')
        
        if not attempts.exists():
            messages.error(request, 'У выбранного пользователя нет завершенных попыток по этому тесту.')
            return redirect('group_results')
        
        attempt = attempts.first()
    
    # Находим сессию зачета, к которой относится эта попытка
    session_id = None
    try:
        participant = QuizParticipant.objects.get(progress=attempt)
        session_id = participant.quiz_session.id
    except QuizParticipant.DoesNotExist:
        # Если это не зачет, ищем сессию по question_order
        try:
            quiz_session = QuizSession.objects.filter(question_order=attempt.question_order).first()
            if quiz_session:
                session_id = quiz_session.id
        except:
            pass

    # Определяем вопросы на основе типа теста
    if attempt.test_type == 'express' or attempt.test_type == 'quiz':
        # Для экспресс-теста и зачета используем сохраненный порядок вопросов
        if attempt.question_order:
            # Получаем вопросы в сохраненном порядке
            question_ids = attempt.question_order
            questions = []
            for q_id in question_ids:
                try:
                    question = Question.objects.get(id=q_id, test=test)
                    questions.append(question)
                except Question.DoesNotExist:
                    continue
            total_questions = len(questions)
        else:
            # Если порядок не сохранен, используем вопросы по порядку номеров
            questions_query = test.questions.all()
            if attempt.start_question:
                questions_query = questions_query.filter(question_number__gte=attempt.start_question)
            if attempt.end_question:
                questions_query = questions_query.filter(question_number__lte=attempt.end_question)
            questions = list(questions_query.order_by('question_number'))
            total_questions = len(questions)
    else:
        # Для обычного теста используем реальный диапазон из прогресса
        questions_query = test.questions.all()
        if attempt.start_question:
            questions_query = questions_query.filter(question_number__gte=attempt.start_question)
        if attempt.end_question:
            questions_query = questions_query.filter(question_number__lte=attempt.end_question)
        questions = list(questions_query.order_by('question_number'))
        total_questions = len(questions)
    
    # Создаем список вопросов с их порядковыми номерами в тесте
    questions_with_order = []
    correct_answers = 0
    user_answers = {}
    
    for i, question in enumerate(questions, 1):
        user_answer = attempt.answers.get(str(question.id), [])
        user_answers[str(question.id)] = user_answer
        
        # ПРАВИЛЬНОЕ ПРЕОБРАЗОВАНИЕ ПРАВИЛЬНЫХ ОТВЕТОВ
        correct_answers_list = []
        try:
            # Обрабатываем случай, когда correct_answer может быть пустым или содержать нечисловые значения
            if question.correct_answer:
                correct_parts = question.correct_answer.split(',')
                for part in correct_parts:
                    part = part.strip()
                    if part.isdigit():  # Проверяем, что часть является числом
                        correct_answers_list.append(int(part))
        except (ValueError, AttributeError):
            correct_answers_list = []
        
        # ПРАВИЛЬНАЯ ПРОВЕРКА СОВПАДЕНИЯ ОТВЕТОВ
        # Преобразуем user_answer в множество чисел для сравнения
        user_answer_set = set(int(ans) for ans in user_answer if str(ans).isdigit())
        correct_answers_set = set(correct_answers_list)
        
        is_correct = user_answer_set == correct_answers_set
        if is_correct:
            correct_answers += 1
        
        questions_with_order.append({
            'question': question,
            'order_number': i,
            'original_number': question.question_number,
            'correct_answers_list': correct_answers_list,
            'is_correct': is_correct
        })
    
    score = (correct_answers / total_questions) * 100 if total_questions > 0 else 0
    
    return render(request, 'tests/user_test_results.html', {
        'target_user': target_user,
        'test': test,
        'attempt': attempt,
        'questions_with_order': questions_with_order,
        'user_answers': user_answers,
        'correct_answers': correct_answers,
        'total_questions': total_questions,
        'score': score,
        'session_id': session_id,
    })

# Функции для проведения зачета

@login_required
def create_quiz(request):
    """Создание зачета для группы"""
    user_profile = request.user.profile
    
    # Проверяем права доступа
    if not user_profile.can_view_other_results():
        messages.error(request, 'У вас нет прав для создания зачетов')
        return redirect('profile')
    
    if request.method == 'POST':
        form = QuizCreationForm(request.POST)
        if form.is_valid():
            test = form.cleaned_data['test']
            question_count = form.cleaned_data['question_count']
            time_limit_minutes = form.cleaned_data['time_limit_minutes']
            starts_at = form.cleaned_data['starts_at']
            ends_at = form.cleaned_data['ends_at']
            
            # Получаем пользователей группы с помощью нового метода
            group_users = user_profile.get_group_users()
            
            # ВКЛЮЧАЕМ СОЗДАТЕЛЯ В СПИСОК УЧАСТНИКОВ
            all_users = list(group_users) 
            all_users.append(request.user)  # Явно добавляем создателя
            
            if not all_users:
                messages.error(request, 'В вашей группе нет пользователей')
                return render(request, 'tests/create_quiz.html', {'form': form})
            
            # Получаем все вопросы теста
            all_questions = list(test.questions.all())
            
            if len(all_questions) < question_count:
                messages.error(request, f'В тесте только {len(all_questions)} вопросов, нельзя создать зачет с {question_count} вопросами')
                return render(request, 'tests/create_quiz.html', {'form': form})
            
            # Выбираем случайные вопросы
            random_questions = random.sample(all_questions, question_count)
            question_order = [q.id for q in random_questions]
            
            # Создаем сессию зачета (is_active=False по умолчанию)
            quiz_session = QuizSession.objects.create(
                creator=request.user,
                test=test,
                question_count=question_count,
                time_limit_minutes=time_limit_minutes,
                starts_at=starts_at,
                ends_at=ends_at,
                question_order=question_order,
                is_active=False,
                manually_activated=False
            )
            
            # Добавляем ВСЕХ участников (включая создателя)
            for user in all_users:
                # Проверяем, не создаем ли дубликат
                if not QuizParticipant.objects.filter(quiz_session=quiz_session, user=user).exists():
                    QuizParticipant.objects.create(
                        quiz_session=quiz_session,
                        user=user
                    )
            
            messages.success(request, f'Зачет создан! Участников: {len(all_users)} (включая вас). Зачет будет активирован автоматически в {starts_at.strftime("%d.%m.%Y %H:%M")} или вы можете активировать его вручную.')
            return redirect('quiz_session_detail', session_id=quiz_session.id)
    
    else:
        form = QuizCreationForm()
    
    return render(request, 'tests/create_quiz.html', {'form': form})

@login_required
def quiz_sessions(request):
    """Список сессий зачетов - ДОСТУПНО ВСЕМ ПОЛЬЗОВАТЕЛЯМ"""
    # Для создателей - созданные зачеты
    created_sessions = QuizSession.objects.filter(creator=request.user).order_by('-created_at')
    
    # Для всех пользователей - зачеты, в которых они участвуют
    # ИСКЛЮЧАЕМ УСЛОВИЕ exclude(creator=request.user) чтобы создатель видел свои зачеты
    participant_sessions = QuizSession.objects.filter(
        participants__user=request.user
    ).order_by('-created_at')
    
    return render(request, 'tests/quiz_sessions.html', {
        'created_sessions': created_sessions,
        'participant_sessions': participant_sessions,
    })

@login_required
def quiz_session_detail(request, session_id):
    """Детальная информация о сессии зачета"""
    quiz_session = get_object_or_404(QuizSession, id=session_id)
    
    # Проверяем и обновляем статус активации
    quiz_session.check_activation()
    
    # Проверяем права доступа
    if (quiz_session.creator != request.user and 
        not quiz_session.participants.filter(user=request.user).exists()):
        messages.error(request, 'У вас нет доступа к этой сессии зачета')
        return redirect('quiz_sessions')
    
    # Получаем участников и сортируем по фамилии
    participants = quiz_session.participants.select_related(
        'user', 'user__profile', 'progress'
    ).all().order_by('user__profile__last_name', 'user__profile__first_name')
    
    # ПРИНУДИТЕЛЬНО ОБНОВЛЯЕМ СТАТУСЫ ВСЕХ УЧАСТНИКОВ
    for participant in participants:
        if participant.progress and participant.progress.completed and not participant.completed_at:
            participant.completed_at = participant.progress.completed_at
            participant.save()
    
    # Считаем завершивших
    completed_count = participants.filter(completed_at__isnull=False).count()
    
    return render(request, 'tests/quiz_session_detail.html', {
        'quiz_session': quiz_session,
        'participants': participants,
        'completed_count': completed_count,
        'total_participants': participants.count(),
        'is_creator': quiz_session.creator == request.user
    })

@login_required
def participate_in_quiz(request, session_id):
    """Участие в зачете"""
    quiz_session = get_object_or_404(QuizSession, id=session_id)
    
    # Проверяем и обновляем статус активации
    quiz_session.check_activation()
    
    # Проверяем, является ли пользователь участником
    participant = get_object_or_404(
        QuizParticipant, 
        quiz_session=quiz_session, 
        user=request.user
    )
    
    # Проверяем, активирован ли зачет
    if not quiz_session.is_active:
        messages.error(request, 'Зачет еще не активирован.')
        return redirect('quiz_session_detail', session_id=session_id)
    
    # Проверяем время зачета
    now = timezone.now()
    if now > quiz_session.ends_at:
        messages.error(request, 'Время зачета истекло')
        return redirect('quiz_session_detail', session_id=session_id)
    
    # Проверяем, не завершил ли уже пользователь зачет
    if participant.progress and participant.progress.completed:
        # Если зачет уже завершен, перенаправляем на страницу результатов С attempt_id
        return redirect('test_results', test_id=quiz_session.test.id) + f'?attempt_id={participant.progress.attempt_id}'
    
    # Создаем или получаем прогресс теста
    if not participant.progress:
        # Создаем прогресс теста
        questions = Question.objects.filter(id__in=quiz_session.question_order)
        first_question = questions.first()
        
        # Рассчитываем время окончания теста
        end_time = now + timezone.timedelta(minutes=quiz_session.time_limit_minutes)
        
        progress = UserTestProgress.objects.create(
            user=request.user,
            test=quiz_session.test,
            current_question=first_question,
            completed=False,
            answers={},
            start_question=1,
            end_question=quiz_session.question_count,
            test_type='quiz',
            time_limit_minutes=quiz_session.time_limit_minutes,
            question_order=quiz_session.question_order,
            start_time=now,
            end_time=end_time,
            quiz_session=quiz_session
        )
        
        participant.progress = progress
        participant.save()
    else:
        progress = participant.progress
        
        # Если прогресс уже существует, но время вышло - завершаем тест
        if progress.end_time and timezone.now() > progress.end_time:
            progress.completed = True
            progress.save()
            messages.error(request, 'Время зачета истекло')
            return redirect('test_results', test_id=quiz_session.test.id)
    
    # Сохраняем в сессии
    request.session['current_attempt_id'] = progress.attempt_id
    request.session['question_range'] = {
        'start': 1,
        'end': quiz_session.question_count,
        'question_ids': quiz_session.question_order,
        'test_type': 'quiz'
    }
    
    return redirect('test_progress', test_id=quiz_session.test.id)


@login_required
def update_quiz_participants(request, session_id):
    """Ручное обновление участников зачета"""
    quiz_session = get_object_or_404(QuizSession, id=session_id)
    
    # Проверяем права доступа
    if quiz_session.creator != request.user:
        messages.error(request, 'Только создатель зачета может обновлять список участников.')
        return redirect('quiz_session_detail', session_id=session_id)
    
    # Получаем всех пользователей группы создателя
    creator_profile = request.user.profile
    group_users = creator_profile.get_group_users()
    
    # Добавляем создателя, если его нет
    if request.user not in group_users:
        group_users = list(group_users) + [request.user]
    
    added_count = 0
    existing_count = 0
    
    # Добавляем всех пользователей группы в зачет
    for user in group_users:
        if not QuizParticipant.objects.filter(
            quiz_session=quiz_session, 
            user=user
        ).exists():
            QuizParticipant.objects.create(
                quiz_session=quiz_session,
                user=user
            )
            added_count += 1
        else:
            existing_count += 1
    
    messages.success(request, f'Добавлено {added_count} новых участников в зачет. Уже было: {existing_count}.')
    return redirect('quiz_session_detail', session_id=session_id)
    

@login_required
def quiz_session_results(request, session_id):
    """Результаты сессии зачета"""
    quiz_session = get_object_or_404(QuizSession, id=session_id)
    
    # Проверяем права доступа - разрешаем не только создателю, но и всем с правами просмотра в этой группе
    user_profile = request.user.profile
    if quiz_session.creator != request.user and not user_profile.can_view_other_results():
        messages.error(request, 'Только создатель зачета может просматривать результаты')
        return redirect('quiz_sessions')
    
    # Получаем участников - создатель видит всех, другие руководители видят только свою группу
    if quiz_session.creator == request.user:
        participants = quiz_session.participants.select_related(
            'user', 'user__profile', 'progress'
        ).all()
    else:
        # Для других руководителей - только участников из их группы
        viewable_users = user_profile.get_viewable_users_query()
        participants = quiz_session.participants.select_related(
            'user', 'user__profile', 'progress'
        ).filter(user__in=viewable_users)
    
    # ПРИНУДИТЕЛЬНО ОБНОВЛЯЕМ СТАТУСЫ ВСЕХ УЧАСТНИКОВ
    for participant in participants:
        if participant.progress and participant.progress.completed and not participant.completed_at:
            participant.completed_at = participant.progress.completed_at
            participant.save()
    
    # СОРТИРУЕМ УЧАСТНИКОВ:
    # 1. Сначала завершившие тест, затем незавершившие
    # 2. Среди завершивших - по результату (от большего к меньшему)
    # 3. При одинаковом результате - по времени завершения (раньше завершившие выше)
    sorted_participants = sorted(
        participants,
        key=lambda p: (
            # Приоритет: завершившие тест идут первыми
            0 if p.completed_at else 1,
            # Для завершивших: результат от большего к меньшему
            -p.progress.score if p.progress and p.progress.score is not None else 1,
            # При одинаковом результате: кто раньше завершил - тот выше
            p.completed_at if p.completed_at else timezone.now()
        )
    )
    
    # Считаем статистику
    completed_participants = [p for p in sorted_participants if p.completed_at]
    avg_score = 0
    if completed_participants:
        avg_score = sum(p.progress.score for p in completed_participants if p.progress) / len(completed_participants)
    
    return render(request, 'tests/quiz_session_results.html', {
        'quiz_session': quiz_session,
        'participants': sorted_participants,  # Используем отсортированный список
        'completed_count': len(completed_participants),
        'total_count': len(sorted_participants),
        'avg_score': round(avg_score, 1)
    })

@login_required
def start_quiz_session(request, session_id):
    """Принудительное начало зачета (для создателя)"""
    quiz_session = get_object_or_404(QuizSession, id=session_id)
    
    # Проверяем права доступа
    if quiz_session.creator != request.user:
        messages.error(request, 'Только создатель зачета может его активировать')
        return redirect('quiz_sessions')
    
    # Принудительно активируем зачет
    quiz_session.activate_manually()
    
    messages.success(request, 'Зачет активирован! Участники теперь могут начать тестирование.')
    return redirect('quiz_session_detail', session_id=session_id)

@login_required
def delete_quiz_session(request, session_id):
    """Удаление сессии зачета"""
    quiz_session = get_object_or_404(QuizSession, id=session_id)
    
    # Проверяем права доступа - только создатель может удалить зачет
    if quiz_session.creator != request.user:
        messages.error(request, 'Вы можете удалять только свои зачеты.')
        return redirect('quiz_sessions')
    
    if request.method == 'POST':
        # Получаем название теста для сообщения
        test_name = quiz_session.test.name
        
        # Удаляем зачет и всех участников (прогресс тестов остается в истории)
        quiz_session.delete()
        
        messages.success(request, f'Зачет "{test_name}" был успешно удален.')
        return redirect('quiz_sessions')
    
    # Если метод не POST, показываем страницу подтверждения
    return render(request, 'tests/delete_quiz_confirm.html', {
        'quiz_session': quiz_session
    })

# tests/views.py - добавим новую функцию

@login_required
def user_test_all_attempts(request, user_id, test_id):
    """Отображение всех попыток пользователя по конкретному тесту"""
    # Проверяем права доступа
    if not request.user.profile.can_view_other_results():
        messages.error(request, 'У вас нет прав для просмотра этих результатов.')
        return redirect('profile')
    
    target_user = get_object_or_404(User, id=user_id)
    test = get_object_or_404(Test, id=test_id)
    
    # Проверяем, что текущий пользователь имеет право просматривать статистику target_user
    viewable_users = request.user.profile.get_viewable_users_query()
    if target_user != request.user and target_user not in viewable_users:
        messages.error(request, 'У вас нет прав для просмотра результатов этого пользователя.')
        return redirect('group_results')
    
    # Получаем все завершенные попытки по этому тесту, отсортированные от последней к первой
    all_attempts = UserTestProgress.objects.filter(
        user=target_user,
        test=test,
        completed=True
    ).select_related('test', 'quiz_session').order_by('-completed_at')
    
    # Находим лучшую попытку
    best_attempt = None
    if all_attempts:
        best_attempt = max(all_attempts, key=lambda x: x.score if x.score else 0)
    
    return render(request, 'tests/user_test_all_attempts.html', {
        'target_user': target_user,
        'test': test,
        'best_attempt': best_attempt,
        'all_attempts': all_attempts,
        'total_attempts': all_attempts.count(),
    })
#Представление для проверки времени
@login_required
@require_GET
def check_time_remaining(request):
    """API endpoint для проверки оставшегося времени"""
    attempt_id = request.GET.get('attempt_id')
    
    if not attempt_id:
        return JsonResponse({'error': 'attempt_id не указан'}, status=400)
    
    try:
        progress = UserTestProgress.objects.get(
            attempt_id=attempt_id, 
            user=request.user
        )
        
        # Проверяем время на сервере
        now = timezone.now()
        if progress.end_time and now > progress.end_time:
            progress.completed = True
            progress.save()
            return JsonResponse({
                'time_expired': True,
                'remaining_time': 0
            })
        
        remaining_time = 0
        if progress.end_time:
            remaining_time = max(0, (progress.end_time - now).total_seconds())
        
        return JsonResponse({
            'time_expired': False,
            'remaining_time': remaining_time
        })
        
    except UserTestProgress.DoesNotExist:
        return JsonResponse({'error': 'Прогресс не найден'}, status=404)


@login_required
def training_statistics(request):
    """Графики статистики тренировок"""
    return statistics_charts(request, request.user, 'normal', 'training_statistics')

@login_required
def express_statistics(request):
    """Графики статистики экспресс-тестов"""
    return statistics_charts(request, request.user, 'express', 'express_statistics')

@login_required
def quiz_statistics(request):
    """Графики статистики зачетов"""
    return statistics_charts(request, request.user, 'quiz', 'quiz_statistics')

@login_required
def all_statistics(request):
    """Графики общей статистики"""
    return statistics_charts(request, request.user, 'all', 'all_statistics')

@login_required
def user_training_statistics(request, user_id):
    """Графики статистики тренировок для другого пользователя"""
    target_user = get_object_or_404(User, id=user_id)
    return user_statistics_charts(request, target_user, 'normal', 'user_training_statistics')

@login_required
def user_express_statistics(request, user_id):
    """Графики статистики экспресс-тестов для другого пользователя"""
    target_user = get_object_or_404(User, id=user_id)
    return user_statistics_charts(request, target_user, 'express', 'user_express_statistics')

@login_required
def user_quiz_statistics(request, user_id):
    """Графики статистики зачетов для другого пользователя"""
    target_user = get_object_or_404(User, id=user_id)
    return user_statistics_charts(request, target_user, 'quiz', 'user_quiz_statistics')

@login_required
def user_all_statistics(request, user_id):
    """Графики общей статистики для другого пользователя"""
    target_user = get_object_or_404(User, id=user_id)
    return user_statistics_charts(request, target_user, 'all', 'user_all_statistics')

def statistics_charts(request, user, test_type, current_view):
    """Общая функция для генерации графиков статистики"""
    # Получаем данные за последние 60 дней
    sixty_days_ago = timezone.now() - timezone.timedelta(days=60)
    
    # Базовый запрос
    tests_query = UserTestProgress.objects.filter(
        user=user,
        completed=True,
        completed_at__gte=sixty_days_ago
    )
    
    # Фильтруем по типу теста
    if test_type != 'all':
        tests_query = tests_query.filter(test_type=test_type)
    
    tests = tests_query.order_by('completed_at')
    
    # Подготавливаем данные для графиков
    chart_data = prepare_chart_data(tests, test_type)
    
    # Дополнительная статистика
    total_tests = tests.count()
    avg_score = tests.aggregate(avg=Avg('score'))['avg'] or 0
    best_score = tests.aggregate(best=Max('score'))['best'] or 0
    worst_score = tests.aggregate(worst=Min('score'))['worst'] or 0
    
    # Самые популярные тесты
    popular_tests = tests.values('test__name').annotate(
        count=Count('id'),
        avg_score=Avg('score')
    ).order_by('-count')[:5]
    
    # Определяем правильный шаблон
    if 'user_' in current_view:
        template_name = 'user_statistics_charts.html'
    else:
        template_name = 'statistics_charts.html'
    
    return render(request, template_name, {
        'user': user,
        'target_user': user,  # Добавляем для совместимости
        'test_type': test_type,
        'current_view': current_view,
        'chart_data': chart_data,
        'total_tests': total_tests,
        'avg_score': round(avg_score, 1),
        'best_score': round(best_score, 1),
        'worst_score': round(worst_score, 1),
        'popular_tests': popular_tests,
        'time_period': '60 дней'
    })

def user_statistics_charts(request, target_user, test_type, current_view):
    """Графики статистики для просмотра другими пользователями"""
    # Проверяем права доступа
    if not request.user.profile.can_view_other_results() and request.user != target_user:
        messages.error(request, 'У вас нет прав для просмотра статистики этого пользователя.')
        return redirect('group_results')
    
    # Используем общую функцию, но с другим шаблоном
    return statistics_charts(request, target_user, test_type, current_view)

def prepare_chart_data(tests, test_type):
    """Подготовка данных для графиков"""
    import json
    from collections import defaultdict
    
    # Данные для графика прогресса по времени
    progress_data = []
    scores_by_date = defaultdict(list)
    
    for test in tests:
        date_str = test.completed_at.strftime('%Y-%m-%d')
        scores_by_date[date_str].append(test.score)
    
    # Усредняем результаты по дням
    for date_str, scores in sorted(scores_by_date.items()):
        avg_score = sum(scores) / len(scores)
        progress_data.append({
            'date': date_str,
            'score': round(avg_score, 1)
        })
    
    # ИСПРАВЛЕННАЯ ЛОГИКА: Данные для распределения результатов по 4-балльной системе
    score_distribution = {
        '0-50%': 0,    # неудовлетворительно
        '51-70%': 0,   # удовлетворительно  
        '71-89%': 0,   # хорошо
        '90-100%': 0   # отлично
    }
    
    for test in tests:
        if test.score is not None:
            score = test.score
            if score <= 50:
                score_distribution['0-50%'] += 1
            elif score <= 70:
                score_distribution['51-70%'] += 1
            elif score <= 90:
                score_distribution['71-89%'] += 1
            else:
                score_distribution['90-100%'] += 1
    
    # Данные для графика по тестам
    tests_performance = []
    test_scores = defaultdict(list)
    
    for test in tests:
        if test.score is not None:
            test_scores[test.test.name].append(test.score)
    
    for test_name, scores in test_scores.items():
        tests_performance.append({
            'test': test_name,
            'avg_score': round(sum(scores) / len(scores), 1),
            'count': len(scores)
        })
    
    # Сортируем по среднему результату
    tests_performance.sort(key=lambda x: x['avg_score'], reverse=True)
    
    return {
        'progress_data': json.dumps(progress_data),
        'score_distribution': json.dumps(score_distribution),
        'tests_performance': json.dumps(tests_performance[:10]),  # Топ-10 тестов
        'total_tests': len(tests)
    }


@login_required
def sync_user_quizzes(request):
    """Синхронизация зачетов пользователя при каждом входе"""
    from .models import QuizSession, QuizParticipant
    from django.utils import timezone
    
    user = request.user
    user_profile = user.profile
    
    now = timezone.now()
    
    if user_profile.department_code:
        try:
            # Находим зачеты, созданные руководителями из той же группы
            group_users = user_profile.get_group_users()
            
            # Ищем активные зачеты, где создатель входит в ту же группу
            active_quizzes = QuizSession.objects.filter(
                ends_at__gte=now,
                is_active=True
            )
            
            # Фильтруем зачеты, где создатель в той же группе что и пользователь
            matching_quizzes = []
            for quiz in active_quizzes:
                if quiz.creator in group_users:
                    matching_quizzes.append(quiz)
            
            # Добавляем пользователя в найденные зачеты
            added_count = 0
            for quiz in matching_quizzes:
                if not QuizParticipant.objects.filter(
                    quiz_session=quiz, 
                    user=user
                ).exists():
                    QuizParticipant.objects.create(
                        quiz_session=quiz,
                        user=user
                    )
                    added_count += 1
            
            if added_count > 0:
                messages.info(request, f'Вы добавлены в {added_count} новых зачетов вашей группы.')
                
        except Exception as e:
            print(f"Ошибка при синхронизации зачетов: {e}")
    
    return redirect('test_selection')    