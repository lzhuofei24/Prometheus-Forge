@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion

echo ========================================
echo Prometheus Forge - Start All Services
echo ========================================
echo.
echo This script will start:
echo   1. FastAPI Backend (port 8000)
echo   2. React Frontend (port 5173)
echo   3. All 6 Celery Workers (Agents)
echo.
pause

cd /d %~dp0

echo.
echo [1/8] Starting FastAPI Backend...
start "Prometheus Forge - Backend" cmd /k "conda activate novel-agent && cd /d %~dp0 && uvicorn src.api.main:app --reload --port 8000"

timeout /t 3 /nobreak >nul

echo [2/8] Starting React Frontend...
cd web
start "Prometheus Forge - Frontend" cmd /k "npm run dev"
cd ..

timeout /t 3 /nobreak >nul

echo [3/8] Starting Architect Worker...
start "Celery Worker - Architect" cmd /k "conda activate novel-agent && cd /d %~dp0 && celery -A src.workers.tasks_new worker -n architect@%%h -Q architect_pending -c 1 --loglevel=info -P solo"

timeout /t 2 /nobreak >nul

echo [4/8] Starting Writer Worker...
start "Celery Worker - Writer" cmd /k "conda activate novel-agent && cd /d %~dp0 && celery -A src.workers.tasks_new worker -n writer@%%h -Q writer_pending -c 1 --loglevel=info -P solo"

timeout /t 2 /nobreak >nul

echo [5/8] Starting Critic Worker...
start "Celery Worker - Critic" cmd /k "conda activate novel-agent && cd /d %~dp0 && celery -A src.workers.tasks_new worker -n critic@%%h -Q critic_pending -c 1 --loglevel=info -P solo"

timeout /t 2 /nobreak >nul

echo [6/8] Starting Media Worker...
start "Celery Worker - Media" cmd /k "conda activate novel-agent && cd /d %~dp0 && celery -A src.workers.tasks_new worker -n media@%%h -Q media_pending -c 1 --loglevel=info -P solo"

timeout /t 2 /nobreak >nul

echo [7/8] Starting Knowledge Worker...
start "Celery Worker - Knowledge" cmd /k "conda activate novel-agent && cd /d %~dp0 && celery -A src.workers.tasks_new worker -n knowledge@%%h -Q knowledge_pending -c 1 --loglevel=info -P solo"

timeout /t 2 /nobreak >nul

echo [8/9] Starting Censor Worker...
start "Celery Worker - Censor" cmd /k "conda activate novel-agent && cd /d %~dp0 && celery -A src.workers.tasks_new worker -n censor@%%h -Q censor_pending -c 1 --loglevel=info -P solo"

timeout /t 2 /nobreak >nul

echo [9/9] Starting Central Controller Worker...
start "Celery Worker - Controller" cmd /k "conda activate novel-agent && cd /d %~dp0 && celery -A src.workers.controller_tasks worker -n controller@%%h -Q controller_pending -c 1 --loglevel=info -P solo"

echo.
echo ========================================
echo All Services Started Successfully!
echo ========================================
echo.
echo Services:
echo   - Backend: http://localhost:8000
echo   - Frontend: http://localhost:5173
echo   - Architect Worker (architect_pending)
echo   - Writer Worker (writer_pending)
echo   - Critic Worker (critic_pending)
echo   - Media Worker (media_pending)
echo   - Knowledge Worker (knowledge_pending)
echo   - Censor Worker (censor_pending)
echo   - Controller Worker (controller_pending)
echo.
echo To stop all services, run: stop_all.bat
echo.
pause
