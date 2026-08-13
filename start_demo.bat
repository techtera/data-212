@echo off
REM Start both backend and research agent for manual testing
REM Run from: D:\TERAFAC\AGENTIC-UI\backend

echo Starting Research Agent on port 9000...
start "Research Agent" cmd /k "cd /d %~dp0 && venv\Scripts\python.exe cloud_run\research_agent\main.py"

timeout /t 3 /nobreak > nul

echo Starting Backend on port 8000...
start "Backend" cmd /k "cd /d %~dp0 && venv\Scripts\python.exe -m uvicorn src.main:app --port 8000 --timeout-keep-alive 120"

echo.
echo Both services starting. Wait for "Application startup complete" in both windows.
echo Frontend: http://localhost:3100
echo Backend:  http://localhost:8000
echo Agent:    http://localhost:9000
pause
