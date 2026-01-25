
@echo off
chcp 65001 >nul
echo ========================================
echo Prometheus Forge - Start All Celery Workers
echo ========================================
echo.
echo Starting 5 Agent Workers...
echo.

cd /d %~dp0

echo [1/5] Starting Architect Worker (architect_pending)...
start "Celery Worker - Architect" cmd /k "conda activate novel-agent && cd /d %~dp0 && celery -A src.workers.tasks_new worker -n architect@%%h -Q architect_pending -c 1 --loglevel=info -P solo"

timeout /t 2 /nobreak >nul

echo [2/5] Starting Writer Worker (writer_pending)...
start "Celery Worker - Writer" cmd /k "conda activate novel-agent && cd /d %~dp0 && celery -A src.workers.tasks_new worker -n writer@%%h -Q writer_pending -c 1 --loglevel=info -P solo"

timeout /t 2 /nobreak >nul

echo [3/5] Starting Critic Worker (critic_pending)...
start "Celery Worker - Critic" cmd /k "conda activate novel-agent && cd /d %~dp0 && celery -A src.workers.tasks_new worker -n critic@%%h -Q critic_pending -c 1 --loglevel=info -P solo"

timeout /t 2 /nobreak >nul

echo [4/5] Starting Media Worker (media_pending)...
start "Celery Worker - Media" cmd /k "conda activate novel-agent && cd /d %~dp0 && celery -A src.workers.tasks_new worker -n media@%%h -Q media_pending -c 1 --loglevel=info -P solo"

timeout /t 2 /nobreak >nul

echo [5/6] Starting Knowledge Worker (knowledge_pending)...
start "Celery Worker - Knowledge" cmd /k "conda activate novel-agent && cd /d %~dp0 && celery -A src.workers.tasks_new worker -n knowledge@%%h -Q knowledge_pending -c 1 --loglevel=info -P solo"

timeout /t 2 /nobreak >nul

echo [6/7] Starting Censor Worker (censor_pending)...
start "Celery Worker - Censor" cmd /k "conda activate novel-agent && cd /d %~dp0 && celery -A src.workers.tasks_new worker -n censor@%%h -Q censor_pending -c 1 --loglevel=info -P solo"

timeout /t 2 /nobreak >nul

echo [7/7] Starting Central Controller Worker (controller_pending)...
start "Celery Worker - Controller" cmd /k "conda activate novel-agent && cd /d %~dp0 && set CELERY_WORKER_NAME=controller && celery -A src.workers.controller_tasks worker -n controller@%%h -Q controller_pending -c 1 --loglevel=info -P solo"

echo.
echo ========================================
echo All 7 Workers Started Successfully!
echo ========================================
echo.
echo Workers:
echo   - Architect (architect_pending)
echo   - Writer (writer_pending)
echo   - Critic (critic_pending)
echo   - Media (media_pending)
echo   - Knowledge (knowledge_pending)
echo   - Censor (censor_pending)
echo   - Controller (controller_pending)
echo.
pause
