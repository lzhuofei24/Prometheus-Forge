@echo off
REM 全链路 E2E 系统测试（Mock AI，无需真实 API / Redis / Worker）
REM 需在项目环境中运行（conda activate novel-agent 或项目 venv），且安装 celery、fakeredis。
REM 传入 tests/e2e 时 tests/conftest 会跳过 app 导入；缺 celery 时整批 E2E 会 SKIP。
cd /d "%~dp0.."
if not defined PYTHONPATH set PYTHONPATH=%cd%
python -m pytest tests/e2e -v -s
exit /b %ERRORLEVEL%
