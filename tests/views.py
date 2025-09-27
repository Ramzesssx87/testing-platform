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
from .models import Test, Question, UserTestProgress
from .forms import TestSelectionForm, CustomUserCreationForm, ExcelUploadForm, ExpressTestForm
from .forms import UserEditForm, UserProfileForm
from django.utils.safestring import mark_safe
from django.http import HttpResponse
from openpyxl import Workbook
from django.views.decorators.http import require_GET

def register_view(request):
    if request.method == 'POST':
        form = CustomUserCreationForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            messages.success(request, f'Добро пожаловать, {user.username}! Регистрация прошла успешно.')
            return redirect('test_selection')
        else:
            messages.error(request, 'Пожалуйста, исправьте ошибки в форме.')
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
    normal_form = TestSelectionForm()
    express_form = ExpressTestForm()
    
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
        'progress_info': progress_info
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
    
    # Логика обработки POST-запроса (ответ на вопрос)
    if request.method == 'POST':
        selected_answers = request.POST.getlist('answer')
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
        
        if next_question:
            progress.current_question = next_question
            progress.save()
        else:
            progress.completed = True
            progress.save()
            return redirect('test_results', test_id=test_id)
        
        # Передаем текст вопроса в шаблон
        return render(request, 'tests/answer_feedback.html', {
            'is_correct': is_correct,
            'correct_answers': correct_answers,
            'answer_options': current_question.answer_options,
            'document_reference': current_question.document_reference,
            'test': test,
            'next_question': next_question,
            'question_text': current_question.question_text
        })
    
    return render(request, 'tests/test_progress.html', {
        'test': test,
        'question': current_question,
        'progress': progress,
        'question_number': question_index,
        'total_questions': total_questions,
        'test_type': test_type
    })

@login_required
def test_results(request, test_id):
    test = get_object_or_404(Test, id=test_id)
    
    # Получаем attempt_id из GET-параметра или из сессии
    attempt_id = request.GET.get('attempt_id') or request.session.get('current_attempt_id')
    
    if not attempt_id:
        messages.error(request, 'Сессия теста не найдена.')
        return redirect('test_selection')
    
    try:
        progress = UserTestProgress.objects.get(attempt_id=attempt_id, user=request.user, test=test)
    except UserTestProgress.DoesNotExist:
        messages.error(request, 'Результаты теста не найдены.')
        return redirect('test_selection')
    
    # Получаем вопросы на основе типа теста
    if progress.test_type == 'express':
        # Для экспресс-теста используем сохраненный порядок вопросов из сессии
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
    for i, question in enumerate(questions, 1):
        questions_with_order.append({
            'question': question,
            'order_number': i,  # Порядковый номер в тесте (1, 2, 3...)
            'original_number': question.question_number  # Оригинальный номер вопроса (119, 418...)
        })
    
    # Считаем правильные ответы
    correct_answers = 0
    user_answers = {}
    
    for item in questions_with_order:
        question = item['question']
        user_answer = progress.answers.get(str(question.id), [])
        user_answers[str(question.id)] = user_answer
        correct_answers_list = [int(ans.strip()) for ans in question.correct_answer.split(',')]
        if set(user_answer) == set(correct_answers_list):
            correct_answers += 1
    
    score = (correct_answers / total_questions) * 100 if total_questions > 0 else 0
    
    # Обновляем результат в прогресс теста (если еще не обновлено)
    if not progress.completed:
        progress.score = score
        progress.correct_answers_count = correct_answers
        progress.total_questions_count = total_questions
        progress.completed = True
        progress.completed_at = timezone.now()
        progress.save()
    
    return render(request, 'tests/test_results.html', {
        'test': test,
        'progress': progress,
        'correct_answers': correct_answers,
        'total_questions': total_questions,
        'score': score,
        'questions_with_order': questions_with_order,  # Передаем вопросы с порядковыми номерами
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
        user_form = UserEditForm(request.POST, instance=request.user)
        profile_form = UserProfileForm(request.POST, instance=request.user.profile)
        
        if user_form.is_valid() and profile_form.is_valid():
            # Сохраняем данные пользователя
            user = user_form.save()
            
            # Сохраняем данные профиля
            profile = profile_form.save(commit=False)
            
            # Обновляем стандартные поля User из профиля
            user.first_name = profile_form.cleaned_data['first_name']
            user.last_name = profile_form.cleaned_data['last_name']
            user.save()
            
            profile.save()
            
            messages.success(request, 'Ваш профиль успешно обновлен!')
            return redirect('profile')
        else:
            messages.error(request, 'Пожалуйста, исправьте ошибки в форме.')
    else:
        user_form = UserEditForm(instance=request.user)
        profile_form = UserProfileForm(instance=request.user.profile)
        # Устанавливаем начальные значения для полей ФИО
        profile_form.fields['first_name'].initial = request.user.first_name
        profile_form.fields['last_name'].initial = request.user.last_name
    
    return render(request, 'edit_profile.html', {
        'user_form': user_form,
        'profile_form': profile_form
    })

@login_required
def statistics(request):
    """Статистика тестов пользователя - теперь использует общую функцию"""
    return statistics_for_user(request, request.user, is_own_profile=True)

@login_required
@require_POST
def reset_statistics(request):
    """Сброс статистики пользователя и удаление старых записей"""
    # Удаляем все завершенные тесты пользователя
    deleted_count = UserTestProgress.objects.filter(
        user=request.user,
        completed=True
    ).delete()[0]
    
    messages.success(request, f'Статистика сброшена. Удалено записей: {deleted_count}')
    return redirect('statistics')

@login_required
def delete_test_progress(request, test_id):
    test = get_object_or_404(Test, id=test_id)
    
    # Получаем попытку из GET-параметра или из сессии
    attempt_id = request.GET.get('attempt_id') or request.session.get('current_attempt_id')
    
    if attempt_id:
        try:
            progress = UserTestProgress.objects.get(attempt_id=attempt_id, user=request.user, test=test)
            
            # Если удаляемая попытка является текущей в сессии, очищаем сессию
            if request.session.get('current_attempt_id') == attempt_id:
                if 'current_attempt_id' in request.session:
                    del request.session['current_attempt_id']
                if 'question_range' in request.session:
                    del request.session['question_range']
            
            # Удаляем прогресс
            progress.delete()
            messages.success(request, f'Прогресс по тесту "{test.name}" был удален.')
            
        except UserTestProgress.DoesNotExist:
            messages.error(request, 'Прогресс теста не найден.')
    else:
        messages.error(request, 'Идентификатор попытки не указан.')
    
    return redirect('test_selection')

@login_required
def group_results(request):
    """Просмотр результатов тестов пользователей в группе - только лучшие результаты экспресс-тестов"""
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
    
    # Фильтрация по тесту, если указан
    test_filter = request.GET.get('test')
    if test_filter:
        completed_tests = completed_tests.filter(test_id=test_filter)
    
    # Фильтрация по дате
    date_from = request.GET.get('date_from')
    date_to = request.GET.get('date_to')
    if date_from:
        completed_tests = completed_tests.filter(completed_at__gte=date_from)
    if date_to:
        completed_tests = completed_tests.filter(completed_at__lte=date_to)
    
    # Собираем лучшие результаты для каждого пользователя и теста
    best_results_dict = {}
    
    for test_progress in completed_tests:
        user_id = test_progress.user.id
        test_id = test_progress.test.id
        
        # Ключ: пользователь + тест (даже если фильтр не выбран, чтобы показывать лучший результат по каждому тесту)
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
    
    # Если фильтр по тесту не выбран, показываем только один лучший результат для каждого пользователя
    if not test_filter:
        user_best_results = {}
        for test_progress in best_results:
            user_id = test_progress.user.id
            if user_id not in user_best_results or test_progress.score > user_best_results[user_id].score:
                user_best_results[user_id] = test_progress
        best_results = list(user_best_results.values())
    
    # Сортируем по убыванию результата
    best_results.sort(key=lambda x: x.score, reverse=True)
    
    # Получаем список доступных тестов для фильтра (только те, по которым есть экспресс-тесты)
    available_tests = Test.objects.filter(
        usertestprogress__user__in=viewable_users,
        usertestprogress__completed=True,
        usertestprogress__test_type='express'  # Только тесты с экспресс-попытками
    ).distinct()
    
    # Статистика по группе
    total_users = viewable_users.count()
    total_tests = len(best_results)
    
    # Средний балл по группе
    if best_results:
        avg_score = sum(result.score for result in best_results) / len(best_results)
    else:
        avg_score = 0
    
    return render(request, 'tests/group_results.html', {
        'viewable_users': viewable_users,
        'completed_tests': best_results,
        'available_tests': available_tests,
        'total_users': total_users,
        'total_tests': total_tests,
        'avg_score': round(avg_score, 1),
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
    # Автоматически удаляем тесты старше 2 месяцев (только для своего профиля)
    if is_own_profile:
        two_months_ago = timezone.now() - timezone.timedelta(days=60)
        old_tests = UserTestProgress.objects.filter(
            user=target_user,
            completed_at__lt=two_months_ago
        )
        old_tests_count = old_tests.count()
        old_tests.delete()
        
        if old_tests_count > 0:
            messages.info(request, f'Автоматически удалено {old_tests_count} записей старше 2 месяцев.')
    
    # Получаем все завершенные тесты (только за последние 2 месяца)
    two_months_ago = timezone.now() - timezone.timedelta(days=60)
    all_completed_tests = UserTestProgress.objects.filter(
        user=target_user,
        completed=True,
        completed_at__gte=two_months_ago
    ).select_related('test').order_by('-completed_at')
    
    # Разделяем на тренировки и экспресс-тесты
    training_tests = all_completed_tests.filter(test_type='normal')
    express_tests = all_completed_tests.filter(test_type='express')
    
    # Общая статистика
    total_trainings = training_tests.count()
    total_express_tests = express_tests.count()
    total_all_tests = all_completed_tests.count()
    
    # Средний результат за последние 10 тренировок
    last_10_trainings = list(training_tests[:10])
    if last_10_trainings:
        training_scores = [test.score for test in last_10_trainings if test.score is not None]
        average_training_last_10 = sum(training_scores) / len(training_scores) if training_scores else 0
    else:
        average_training_last_10 = 0
    
    # Средний результат за последние 10 экспресс-тестов
    last_10_express = list(express_tests[:10])
    if last_10_express:
        express_scores = [test.score for test in last_10_express if test.score is not None]
        average_express_last_10 = sum(express_scores) / len(express_scores) if express_scores else 0
    else:
        average_express_last_10 = 0
    
    # Для таблиц - ограничиваем показ последними 10
    training_tests_limited = list(training_tests[:10])
    express_tests_limited = list(express_tests[:10])
    
    # Определяем, нужно ли показывать кнопки "Показать все"
    has_more_trainings = total_trainings > 10
    has_more_express = total_express_tests > 10
    
    template_name = 'statistics.html' if is_own_profile else 'user_statistics_view.html'
    
    return render(request, template_name, {
        'target_user': target_user,
        'is_own_profile': is_own_profile,
        'total_trainings': total_trainings,
        'total_express_tests': total_express_tests,
        'total_all_tests': total_all_tests,
        'average_training_last_10': round(average_training_last_10, 1),
        'average_express_last_10': round(average_express_last_10, 1),
        'training_tests': training_tests,
        'training_tests_limited': training_tests_limited,
        'express_tests': express_tests,
        'express_tests_limited': express_tests_limited,
        'has_more_trainings': has_more_trainings,
        'has_more_express': has_more_express,
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
    if target_user not in viewable_users:
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
    
    # Определяем вопросы на основе типа теста
    if attempt.test_type == 'express':
        # Для экспресс-теста используем сохраненный порядок вопросов
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
    for i, question in enumerate(questions, 1):
        questions_with_order.append({
            'question': question,
            'order_number': i,  # Порядковый номер в тесте (1, 2, 3...)
            'original_number': question.question_number  # Оригинальный номер вопроса (345, 245, 23...)
        })
    
    # Считаем правильные ответы для этой попытки
    correct_answers = 0
    user_answers = {}
    
    for item in questions_with_order:
        question = item['question']
        user_answer = attempt.answers.get(str(question.id), [])
        user_answers[str(question.id)] = user_answer
        correct_answers_list = [int(ans.strip()) for ans in question.correct_answer.split(',')]
        if set(user_answer) == set(correct_answers_list):
            correct_answers += 1
    
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
    })