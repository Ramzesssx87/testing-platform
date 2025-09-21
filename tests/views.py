import json
import tempfile
import os
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login, authenticate, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import AuthenticationForm
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from django.contrib import messages
from django.db.models import Count
from .models import Test, Question, UserTestProgress
from .forms import TestSelectionForm, CustomUserCreationForm, ExcelUploadForm
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
            return redirect('test_selection')
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
    if request.method == 'POST':
        form = TestSelectionForm(request.POST)
        if form.is_valid():
            test = form.cleaned_data['test']
            start_question = form.cleaned_data['start_question']
            end_question = form.cleaned_data['end_question']
            
            # Получаем вопросы в выбранном диапазоне
            questions_query = test.questions.all()
            
            if start_question:
                questions_query = questions_query.filter(question_number__gte=start_question)
            
            if end_question:
                questions_query = questions_query.filter(question_number__lte=end_question)
            
            questions = list(questions_query)
            
            if not questions:
                form.add_error(None, "В выбранном диапазоне нет вопросов")
                return render(request, 'tests/test_selection.html', {'form': form})
            
            # Всегда сбрасываем прогресс при выборе теста
            progress, created = UserTestProgress.objects.update_or_create(
                user=request.user,
                test=test,
                defaults={
                    'current_question': questions[0],
                    'completed': False,
                    'answers': {},
                    'start_question': start_question,
                    'end_question': end_question
                }
            )
            
            # Сохраняем диапазон вопросов в сессии
            request.session['question_range'] = {
                'start': start_question,
                'end': end_question,
                'question_ids': [q.id for q in questions]
            }
            
            return redirect('test_progress', test_id=test.id)
    else:
        form = TestSelectionForm()
    
    user_progress = UserTestProgress.objects.filter(user=request.user)
    
    # Создаем список для хранения информации о прогрессе с учетом диапазона
    progress_info = []
    for progress in user_progress:
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
        'form': form,
        'progress_info': progress_info
    })

@login_required
def test_progress(request, test_id):
    test = get_object_or_404(Test, id=test_id)
    
    # Получаем сохраненный диапазон вопросов из сессии
    question_range = request.session.get('question_range', {})
    question_ids = question_range.get('question_ids', [])
    
    if question_ids:
        # Используем вопросы из диапазона
        questions = Question.objects.filter(id__in=question_ids).order_by('question_number')
    else:
        # Используем все вопросы
        questions = test.questions.all()
    
    progress, created = UserTestProgress.objects.get_or_create(
        user=request.user,
        test=test,
        defaults={'current_question': questions.first()}
    )
    
    # Если тест завершен, но пользователь хочет начать заново, сбрасываем прогресс
    if progress.completed and 'restart' not in request.GET:
        return redirect('test_results', test_id=test_id)
    
    # Проверяем, что текущий вопрос входит в выбранный диапазон
    if progress.current_question and progress.current_question.id not in question_ids and question_ids:
        progress.current_question = questions.first()
        progress.save()
    
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
            'question_text': current_question.question_text  # Добавляем текст вопроса
        })
    
    return render(request, 'tests/test_progress.html', {
        'test': test,
        'question': current_question,
        'progress': progress,
        'question_number': question_index,
        'total_questions': total_questions
    })

@login_required
def test_results(request, test_id):
    test = get_object_or_404(Test, id=test_id)
    progress = get_object_or_404(UserTestProgress, user=request.user, test=test)
    
    # Получаем сохраненный диапазон вопросов из сессии
    question_range = request.session.get('question_range', {})
    question_ids = question_range.get('question_ids', [])
    
    if question_ids:
        # Используем вопросы из диапазона
        questions = Question.objects.filter(id__in=question_ids).order_by('question_number')
    else:
        # Используем все вопросы
        questions = test.questions.all()
    
    # Считаем правильные ответы
    correct_answers = 0
    # Создаем список для хранения ответов пользователя по каждому вопросу
    user_answers = {}
    for question in questions:
        # Получаем ответ пользователя на вопрос, если его нет, то пустой список
        user_answer = progress.answers.get(str(question.id), [])
        user_answers[str(question.id)] = user_answer
        correct_answers_list = [int(ans.strip()) for ans in question.correct_answer.split(',')]
        if set(user_answer) == set(correct_answers_list):
            correct_answers += 1
    
    total_questions = questions.count()
    score = (correct_answers / total_questions) * 100 if total_questions > 0 else 0
    
    return render(request, 'tests/test_results.html', {
        'test': test,
        'progress': progress,
        'correct_answers': correct_answers,
        'total_questions': total_questions,
        'score': score,
        'questions': questions,
        'user_answers': user_answers
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
    progress = get_object_or_404(UserTestProgress, user=request.user, test=test)
    
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
    progress.save()
    
    # Очищаем диапазон вопросов из сессии
    if 'question_range' in request.session:
        del request.session['question_range']
    
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