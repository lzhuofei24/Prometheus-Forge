@echo off
chcp 65001 >nul 2>&1
cls

echo.
echo ╔════════════════════════════════════════════════════════════════╗
echo ║                                                                ║
echo ║                   Novel-Agent 一键启动                          ║
echo ║            分布式AI小说创作系统 v1.0                            ║
echo ║                                                                ║
echo ╚════════════════════════════════════════════════════════════════╝
echo.
echo.

REM 检查 Conda 环境
echo [1/4] 检查 Conda 环境...
call conda activate novel-agent 2>nul
if %errorlevel% neq 0 (
    echo.
    echo ❌ 错误: novel-agent 环境不存在
    echo.
    echo 请先创建环境:
    echo   conda env create -f environment.yml
    echo   conda activate novel-agent
    echo.
    pause
    exit /b 1
)
echo    ✅ Conda 环境已激活
echo.

REM 检查 Docker
echo [2/4] 检查 Docker Desktop...
docker ps >nul 2>&1
if %errorlevel% neq 0 (
    echo    ❌ Docker Desktop 未运行
    echo.
    echo    请先启动 Docker Desktop，然后重新运行此脚本
    echo.
    pause
    exit /b 1
)
echo    ✅ Docker Desktop 正在运行
echo.

REM 启动 Redis
echo [3/4] 启动 Redis...
docker-compose up -d >nul 2>&1
if %errorlevel% neq 0 (
    echo    ❌ Redis 启动失败
    pause
    exit /b 1
)
echo    ✅ Redis 已启动
timeout /t 2 /nobreak >nul
echo.

REM 启动 Celery Workers
echo [4/4] 启动 Celery Workers...
echo    → 正在启动文本处理 Worker (text_queue)...
start "Novel-Agent Worker [Text]" cmd /k "conda activate novel-agent && cd /d %~dp0 && celery -A src.workers.tasks worker -Q text_queue -c 1 --loglevel=info --pool=solo"

timeout /t 2 /nobreak >nul

echo    → 正在启动多模态 Worker (rag_queue + media_queue)...
start "Novel-Agent Worker [RAG+Media]" cmd /k "conda activate novel-agent && cd /d %~dp0 && celery -A src.workers.tasks worker -Q rag_queue,media_queue -c 2 --loglevel=info --pool=solo"

timeout /t 2 /nobreak >nul
echo    ✅ Workers 已启动
echo.

echo.
echo ╔════════════════════════════════════════════════════════════════╗
echo ║                      启动完成！                                 ║
echo ╚════════════════════════════════════════════════════════════════╝
echo.
echo 📋 后台服务已启动:
echo    • Redis (Docker)
echo    • Celery Worker [Text] - 处理大纲/正文/审稿
echo    • Celery Worker [RAG+Media] - 处理图片/音频
echo.
echo 🌐 下一步: 启动 Web 界面
echo.
echo    在新终端运行:
echo    ^> conda activate novel-agent
echo    ^> streamlit run src/gui/Home.py
echo.
echo    然后访问: http://localhost:8501
echo.
echo 📚 查看文档: docs\README.md
echo 🐛 遇到问题: docs\TROUBLESHOOTING.md
echo.
pause
