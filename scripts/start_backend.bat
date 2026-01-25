@echo off
chcp 65001 >nul
echo ========================================
echo Prometheus Forge Backend Startup
echo ========================================
echo.

echo Please ensure conda environment is activated: novel-agent
echo Please ensure Redis is running: docker-compose up -d redis
echo.

pause

echo Starting FastAPI server...
cd /d %~dp0..
start "Prometheus Forge API" cmd /k "conda activate novel-agent && uvicorn src.api.main:app --reload --port 8000"

echo.
echo ========================================
echo FastAPI server started
echo Access: http://localhost:8000
echo API Docs: http://localhost:8000/docs
echo ========================================
echo.
pause
