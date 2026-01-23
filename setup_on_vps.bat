@echo off
echo ========================================
echo SETTING UP POCKET OPTION ON VPS
echo ========================================
echo VPS: %COMPUTERNAME%
echo User: %USERNAME%
echo Time: %date% %time%
echo.

REM Check if we're on the VPS
if not "%COMPUTERNAME%"=="WIN-*" (
    echo This script should be run on the VPS
    echo Current computer: %COMPUTERNAME%
)

REM Create project directory
echo Creating project directory...
if not exist "C:\pocket_option" mkdir C:\pocket_option
cd /d C:\pocket_option

REM Copy files if running from different location
if exist "%~dp0*.py" (
    echo Copying files from %~dp0...
    xcopy "%~dp0*" "C:\pocket_option\" /E /Y /Q
)

REM Install Python
echo Installing Python...
winget install Python.Python.3.12 --accept-source-agreements --accept-package-agreements --silent

REM Wait for installation
timeout /t 30 /nobreak

REM Refresh environment variables
echo Refreshing environment variables...
for /f "tokens=2*" %%a in ('reg query "HKLM\SYSTEM\CurrentControlSet\Control\Session Manager\Environment" /v PATH') do set "PATH=%%b"
for /f "tokens=2*" %%a in ('reg query "HKCU\Environment" /v PATH') do set "PATH=%PATH%;%%b"

REM Test Python installation
echo Testing Python installation...
python --version
if %errorlevel% neq 0 (
    echo Python installation failed or not in PATH
    echo Please install Python manually and run this script again
    pause
    exit /b 1
)

REM Create virtual environment
echo Creating virtual environment...
python -m venv venv

REM Activate virtual environment
echo Activating virtual environment...
call venv\Scripts\activate.bat

REM Upgrade pip
echo Upgrading pip...
python -m pip install --upgrade pip

REM Install requirements
echo Installing requirements...
pip install -r requirements.txt

echo.
echo ========================================
echo ✅ SETUP COMPLETE!
echo ========================================
echo.
echo To run the trading bot:
echo 1. cd C:\pocket_option
echo 2. venv\Scripts\activate
echo 3. python app.py
echo.
echo Or simply run: C:\pocket_option\run_bot.bat
echo.

REM Create run_bot.bat
echo @echo off > run_bot.bat
echo cd /d C:\pocket_option >> run_bot.bat
echo call venv\Scripts\activate.bat >> run_bot.bat
echo python app.py >> run_bot.bat
echo pause >> run_bot.bat

echo ✅ Created run_bot.bat for easy startup
echo.
echo Would you like to start the trading bot now? (Y/N)
set /p choice=
if /i "%choice%"=="Y" (
    echo Starting trading bot...
    python app.py
)

pause