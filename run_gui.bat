@echo off
chcp 65001 >nul
echo ======================================================
echo   Запуск веб-интерфейса Анализатора Диалогов
echo ======================================================
echo.

if exist .venv\Scripts\activate.bat (
    call .venv\Scripts\activate.bat
)

echo Запуск Streamlit в браузере...
streamlit run app.py
pause
