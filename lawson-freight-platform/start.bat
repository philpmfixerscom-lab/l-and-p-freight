@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    echo Run run.bat once first to install dependencies.
    pause
    exit /b 1
)
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":8502" ^| findstr LISTENING') do taskkill /F /PID %%a 2>nul
timeout /t 1 /nobreak >nul
echo L and P Freight Platform - http://127.0.0.1:8502
".venv\Scripts\python.exe" -m streamlit run app.py --server.address 127.0.0.1 --server.port 8502 --server.headless false
pause