@echo off
chcp 65001 >nul
echo ======================================================
echo   Тестовый прогон анализатора диалогов (Mock-режим)
echo ======================================================
echo.

if exist .venv\Scripts\activate.bat (
    call .venv\Scripts\activate.bat
)

python main.py --mock -i sample_dialogues.xlsx -o analysis_result.xlsx
echo.
pause
