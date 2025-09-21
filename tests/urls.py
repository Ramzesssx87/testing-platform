# tests/urls.py - добавим новый путь
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
    path('save_answer/', views.save_answer, name='save_answer'),
    path('upload-excel/', views.upload_test_excel, name='upload_excel'),
    path('manage-tests/', views.manage_tests, name='manage_tests'),
    path('test/<int:test_id>/export/', views.export_test_excel, name='export_test'),
    path('test/<int:test_id>/export-answers/', views.export_answers_excel, name='export_answers'),  # Новая строка
]