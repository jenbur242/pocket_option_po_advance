@echo off
echo ========================================
echo POCKET OPTION TRADING BOT - VPS
echo ========================================
echo Starting at: %date% %time%
echo VPS: 172.86.111.47
echo.

cd /d C:\pocket_option
call venv\Scripts\activate.bat

echo Virtual environment activated
echo Starting trading bot...
python app.py

pause