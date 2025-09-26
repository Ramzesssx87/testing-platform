@echo off
chcp 65001 > nul
echo Остановка сервера тестирования...
for /f "tokens=5" %%a in ('netstat -ano ^| findstr :8000') do taskkill /f /pid %%a
echo Сервер остановлен.
pause