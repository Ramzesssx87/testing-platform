from django.urls import path
from . import views

urlpatterns = [
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('register/', views.register_view, name='register'),
    path('', views.test_selection, name='test_selection'),
    path('test/<int:test_id>/', views.test_progress, name='test_progress'),
    path('test/<int:test_id>/results/', views.test_results, name='test_results'),
    path('test/<int:test_id>/reset/', views.reset_test_progress, name='reset_test_progress'),
    path('test/<int:test_id>/delete/', views.delete_test_progress, name='delete_test_progress'),
    path('save_answer/', views.save_answer, name='save_answer'),
    path('upload-excel/', views.upload_test_excel, name='upload_excel'),
    path('manage-tests/', views.manage_tests, name='manage_tests'),
    path('test/<int:test_id>/export/', views.export_test_excel, name='export_test'),
    path('test/<int:test_id>/export-answers/', views.export_answers_excel, name='export_answers'),
    path('profile/', views.profile, name='profile'),
    path('profile/edit/', views.edit_profile, name='edit_profile'),
    path('profile/statistics/', views.statistics, name='statistics'),
    path('profile/statistics/reset/', views.reset_statistics, name='reset_statistics'),
    path('group-results/', views.group_results, name='group_results'),
    path('user/<int:user_id>/test/<int:test_id>/results/', views.user_test_results, name='user_test_results'),
    path('user/<int:user_id>/statistics/', views.user_statistics_view, name='user_statistics_view'),
    
    # Проведение зачета
    path('quiz/create/', views.create_quiz, name='create_quiz'),
    path('quiz/sessions/', views.quiz_sessions, name='quiz_sessions'),
    path('quiz/session/<int:session_id>/', views.quiz_session_detail, name='quiz_session_detail'),
    path('quiz/session/<int:session_id>/start/', views.start_quiz_session, name='start_quiz_session'),
    path('quiz/session/<int:session_id>/results/', views.quiz_session_results, name='quiz_session_results'),
    path('quiz/session/<int:session_id>/delete/', views.delete_quiz_session, name='delete_quiz_session'),
    path('quiz/session/<int:session_id>/update-participants/', views.update_quiz_participants, name='update_quiz_participants'),
    path('quiz/participate/<int:session_id>/', views.participate_in_quiz, name='participate_in_quiz'),
     # Новый URL для всех попыток теста пользователя
    path('user/<int:user_id>/test/<int:test_id>/all-attempts/', views.user_test_all_attempts, name='user_test_all_attempts'),
    # Новый URL для проверки времени
    path('check-time-remaining/', views.check_time_remaining, name='check_time_remaining'),
    # Графики статистики
    path('statistics/training/', views.training_statistics, name='training_statistics'),
    path('statistics/express/', views.express_statistics, name='express_statistics'),
    path('statistics/quiz/', views.quiz_statistics, name='quiz_statistics'),
    path('statistics/all/', views.all_statistics, name='all_statistics'),
    
    # Графики для просмотра статистики других пользователей
    path('user/<int:user_id>/statistics/training/', views.user_training_statistics, name='user_training_statistics'),
    path('user/<int:user_id>/statistics/express/', views.user_express_statistics, name='user_express_statistics'),
    path('user/<int:user_id>/statistics/quiz/', views.user_quiz_statistics, name='user_quiz_statistics'),
    path('user/<int:user_id>/statistics/all/', views.user_all_statistics, name='user_all_statistics'),
]