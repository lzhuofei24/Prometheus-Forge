@echo off
chcp 65001 >nul
echo ========================================
echo Prometheus Forge - Stop All Services
echo ========================================
echo.

echo Stopping all services...
echo.

echo [1/3] Stopping FastAPI Backend...
taskkill /FI "WINDOWTITLE eq Prometheus Forge - Backend*" /T /F >nul 2>&1
for /f "tokens=5" %%a in ('netstat -ano ^| findstr :8000 ^| findstr LISTENING') do (
    taskkill /PID %%a /T /F >nul 2>&1
)
taskkill /FI "IMAGENAME eq python.exe" /FI "COMMANDLINE eq *uvicorn*" /T /F >nul 2>&1
wmic process where "commandline like '%%uvicorn%%' and commandline like '%%src.api.main%%'" delete >nul 2>&1

echo [2/3] Stopping React Frontend...
taskkill /FI "WINDOWTITLE eq Prometheus Forge - Frontend*" /T /F >nul 2>&1
for /f "tokens=5" %%a in ('netstat -ano ^| findstr :5173 ^| findstr LISTENING') do (
    taskkill /PID %%a /T /F >nul 2>&1
)
taskkill /FI "IMAGENAME eq node.exe" /FI "COMMANDLINE eq *vite*" /T /F >nul 2>&1
wmic process where "commandline like '%%vite%%' and commandline like '%%dev%%'" delete >nul 2>&1

echo [3/3] Stopping All Celery Workers...
taskkill /FI "WINDOWTITLE eq Celery Worker -*" /T /F >nul 2>&1
taskkill /FI "IMAGENAME eq python.exe" /FI "COMMANDLINE eq *celery*" /FI "COMMANDLINE eq *worker*" /T /F >nul 2>&1
wmic process where "commandline like '%%celery%%' and commandline like '%%worker%%' and commandline like '%%tasks_new%%'" delete >nul 2>&1

for /f "tokens=2" %%a in ('netstat -ano ^| findstr :6379') do (
    set pid=%%a
    for /f "tokens=5" %%b in ('netstat -ano ^| findstr :6379 ^| findstr !pid!') do (
        taskkill /PID %%b /T /F >nul 2>&1
    )
)

echo.
echo ========================================
echo All Services Stopped!
echo ========================================
echo.
echo Stopped services:
echo   - FastAPI Backend (port 8000)
echo   - React Frontend (port 5173)
echo   - All 6 Celery Workers:
echo     * Architect
echo     * Writer
echo     * Critic
echo     * Media
echo     * Knowledge
echo     * Censor
echo.
echo Note: If some processes are still running, you may need to:
echo   1. Check Task Manager
echo   2. Close the windows manually
echo   3. Run this script again with administrator privileges
echo.
pause
