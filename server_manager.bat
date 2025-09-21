@echo off
chcp 65001 > nul
title Управление сервером тестирования НОПРИЗ
echo =======================================
echo    Управление сервером тестирования
echo =======================================
echo.
echo 1. Запустить сервер в фоновом режиме
echo 2. Остановить сервер
echo 3. Проверить статус сервера
echo 4. Выход
echo.
set /p choice="Выберите действие (1-4): "

if "%choice%"=="1" (
    echo Запуск сервера в фоновом режиме...
    wscript "E:\TestNOPRIZ\start_server.vbs"
    echo Сервер запущен в фоновом режиме.
    pause
) else if "%choice%"=="2" (
    echo Остановка сервера...
    for /f "tokens=5" %%a in ('netstat -ano ^| findstr :8000') do taskkill /f /pid %%a
    echo Сервер остановлен.
    pause
) else if "%choice%"=="3" (
    echo Проверка статуса сервера...
    netstat -ano | findstr :8000
    if errorlevel 1 (
        echo Сервер не запущен.
    ) else (
        echo Сервер работает на порту 8000.
    )
    pause
) else (
    exit
)