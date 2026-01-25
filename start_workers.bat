@echo off
chcp 65001 >nul
echo ========================================
echo Prometheus Forge Celery Workers Startup
echo ========================================
echo.

echo Please ensure conda environment is activated: novel-agent
echo Please ensure Redis is running: docker-compose up -d redis
echo.

pause

echo Starting Text Queue Worker (text_queue, concurrency=1)...
cd /d %~dp0
start "Celery Worker - Text Queue" cmd /k "conda activate novel-agent && cd /d %~dp0 && celery -A src.workers.tasks_new worker -n worker-text@%%h -Q text_queue -c 1 --loglevel=info -P solo"

timeout /t 2 /nobreak >nul

echo Starting RAG and Media Queue Worker (rag_queue,media_queue, concurrency=2)...
start "Celery Worker - RAG+Media Queue" cmd /k "conda activate novel-agent && cd /d %~dp0 && celery -A src.workers.tasks_new worker -n worker-media@%%h -Q rag_queue,media_queue -c 2 --loglevel=info -P solo"

echo.
echo ========================================
echo Workers started, check logs in new windows
echo ========================================
echo.
pause
