@echo off
chcp 65001 >nul
echo ======================================================
echo   Установка Анализатора Диалогов (Dialogue Analyzer)
echo ======================================================
echo.

:: Проверка наличия Python
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ОШИБКА] Python не найден в системе!
    echo Пожалуйста, установите Python версии 3.10 или выше с сайта python.org
    echo При установке обязательно отметьте галочку "Add python.exe to PATH".
    echo.
    pause
    exit /b 1
)

echo [1/3] Создание изолированного виртуального окружения (.venv)...
python -m venv .venv
if %errorlevel% neq 0 (
    echo [ОШИБКА] Не удалось создать виртуальное окружение.
    pause
    exit /b 1
)

echo [2/3] Обновление pip...
call .venv\Scripts\activate.bat
python -m pip install --upgrade pip

echo [3/3] Установка необходимых библиотек (pandas, openpyxl, streamlit, requests)...
pip install -r requirements.txt streamlit

echo.
echo ======================================================
echo  [УСПЕХ] Установка успешно завершена!
echo  Для запуска приложения используйте run_gui.bat
echo ======================================================
echo.
pause
