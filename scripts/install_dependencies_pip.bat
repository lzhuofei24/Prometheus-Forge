@echo off
echo ========================================
echo Novel-Agent 依赖安装脚本 (使用 pip)
echo ========================================
echo.

echo 请确保已激活 conda 环境: novel-agent
echo.
pause

echo 正在安装依赖包...
pip install langchain>=0.1.0 langgraph>=0.0.20 chromadb>=0.4.0
pip install openai>=1.0.0 pydantic>=2.0.0 pydantic-settings>=2.0.0
pip install pyyaml>=6.0 colorlog>=6.7.0 jinja2>=3.1.0 python-dotenv>=1.0.0
pip install celery>=5.3.0 redis>=5.0.0 flower>=2.0.0
pip install sentence-transformers>=2.2.0 edge-tts>=6.1.0
pip install requests>=2.31.0 pillow>=10.0.0

if %errorlevel% neq 0 (
    echo.
    echo 错误: 依赖安装失败
    pause
    exit /b 1
)

echo.
echo ========================================
echo 依赖安装完成！
echo.
echo 验证安装:
echo   python check_system.py
echo ========================================
echo.
pause
