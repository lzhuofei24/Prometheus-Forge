@echo off
echo ========================================
echo Novel-Agent 快速依赖安装
echo ========================================
echo.

echo 请确保已激活 conda 环境: novel-agent
echo.
pause

echo 正在安装所有依赖...
pip install langchain>=0.1.0 langgraph>=0.0.20 chromadb>=0.4.0 openai>=1.0.0
pip install pydantic>=2.0.0 pydantic-settings>=2.0.0 pyyaml>=6.0 colorlog>=6.7.0
pip install jinja2>=3.1.0 python-dotenv>=1.0.0 celery>=5.3.0 redis>=5.0.0
pip install flower>=2.0.0 sentence-transformers>=2.2.0 edge-tts>=6.1.0
pip install requests>=2.31.0 pillow>=10.0.0

echo.
echo ========================================
echo 安装完成！验证中...
echo ========================================
echo.

celery --version
python -c "import redis; print('Redis version:', redis.__version__)"
python -c "import chromadb; print('ChromaDB installed')"
python -c "import sentence_transformers; print('Sentence Transformers installed')"

echo.
echo ========================================
echo 验证完成！现在可以启动系统了
echo ========================================
echo.
pause
