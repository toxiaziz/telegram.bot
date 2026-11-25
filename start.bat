@echo off
chcp 65001 >nul
cd /d "%~dp0"

python bot.py
if errorlevel 9009 py bot.py

echo.
echo ==========================================
echo Bot to'xtadi. Yuqoridagi xabarni o'qing.
echo ==========================================
pause
