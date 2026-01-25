@echo off
REM Run this script directly: .\start_all_tabs.bat  or  start_all_tabs.bat
REM Do NOT run with: python start_all_tabs.bat  (this is a batch file, not Python)
chcp 65001 >nul

echo ========================================
echo Prometheus Forge - Starting in Tabs
echo ========================================

:: 定义工作目录
set WORK_DIR=%~dp0
cd /d %WORK_DIR%

:: 构建 WT 命令字符串
:: 注意：cmd /k 后面紧跟 conda activate 命令

set CMD_BACKEND=cmd /k "echo [Backend] && conda activate novel-agent && cd /d %WORK_DIR% && uvicorn src.api.main:app --reload --port 8000"
set CMD_FRONTEND=cmd /k "echo [Frontend] && cd /d %WORK_DIR%web && npm run dev"

:: Celery Workers 命令
set CMD_ARCHITECT=cmd /k "echo [Architect] && conda activate novel-agent && cd /d %WORK_DIR% && celery -A src.workers.tasks_new worker -n architect@%%h -Q architect_pending -c 1 --loglevel=info -P solo"
set CMD_WRITER=cmd /k "echo [Writer] && conda activate novel-agent && cd /d %WORK_DIR% && celery -A src.workers.tasks_new worker -n writer@%%h -Q writer_pending -c 1 --loglevel=info -P solo"
set CMD_CENSOR=cmd /k "echo [Censor] && conda activate novel-agent && cd /d %WORK_DIR% && celery -A src.workers.tasks_new worker -n censor@%%h -Q censor_pending -c 1 --loglevel=info -P solo"
set CMD_CRITIC=cmd /k "echo [Critic] && conda activate novel-agent && cd /d %WORK_DIR% && celery -A src.workers.tasks_new worker -n critic@%%h -Q critic_pending -c 1 --loglevel=info -P solo"
set CMD_MEDIA=cmd /k "echo [Media] && conda activate novel-agent && cd /d %WORK_DIR% && celery -A src.workers.tasks_new worker -n media@%%h -Q media_pending -c 1 --loglevel=info -P solo"
set CMD_KNOWLEDGE=cmd /k "echo [Knowledge] && conda activate novel-agent && cd /d %WORK_DIR% && celery -A src.workers.tasks_new worker -n knowledge@%%h -Q knowledge_pending -c 1 --loglevel=info -P solo"
set CMD_CONTROLLER=cmd /k "echo [Controller] && conda activate novel-agent && cd /d %WORK_DIR% && celery -A src.workers.controller_tasks worker -n controller@%%h -Q controller_pending -c 1 --loglevel=info -P solo"

:: 执行 wt 命令，通过分号 ; 分隔标签页
:: -w 0 表示在当前窗口或新窗口打开
start wt -w 0 ^
  new-tab --title "Backend" %CMD_BACKEND% ; ^
  new-tab --title "Frontend" %CMD_FRONTEND% ; ^
  new-tab --title "Architect" %CMD_ARCHITECT% ; ^
  new-tab --title "Writer" %CMD_WRITER% ; ^
  new-tab --title "Censor" %CMD_CENSOR% ; ^
  new-tab --title "Critic" %CMD_CRITIC% ; ^
  new-tab --title "Media" %CMD_MEDIA% ; ^
  new-tab --title "Knowledge" %CMD_KNOWLEDGE% ; ^
  new-tab --title "Controller" %CMD_CONTROLLER%

echo Services are starting in Windows Terminal tabs...
timeout /t 3 /nobreak >nul 2>nul
