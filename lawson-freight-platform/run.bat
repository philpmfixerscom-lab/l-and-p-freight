@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    echo Creating virtual environment...
    py -3.12 -m venv .venv
)
echo Installing dependencies...
".venv\Scripts\python.exe" -m pip install -q -r requirements.txt
echo Stopping any old instance on port 8502...
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":8502" ^| findstr LISTENING') do taskkill /F /PID %%a 2>nul
timeout /t 2 /nobreak >nul
echo Starting L ^& P Freight Platform at http://127.0.0.1:8502
".venv\Scripts\python.exe" -m streamlit run app.py --server.address 127.0.0.1 --server.port 8502 --server.headless false
pause