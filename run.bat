@echo off
cd /d "%~dp0"
set PYTHON=%LOCALAPPDATA%\Programs\Python\Python313\python.exe
echo Installing dependencies...
"%PYTHON%" -m pip install -r requirements.txt
echo.
echo Starting HR AI Agent...
echo Open your browser at: http://127.0.0.1:5000
echo.
"%PYTHON%" app.py
pause
