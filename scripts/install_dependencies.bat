@echo off
echo ========================================
echo Novel-Agent 依赖安装脚本
echo ========================================
echo.

echo 正在更新 conda 环境...
conda env update -f environment.yml

if %errorlevel% neq 0 (
    echo.
    echo 错误: conda 环境更新失败
    echo 如果环境不存在，请先创建:
    echo   conda env create -f environment.yml
    pause
    exit /b 1
)

echo.
echo ========================================
echo 依赖安装完成！
echo.
echo 下一步:
echo   1. 激活环境: conda activate novel-agent
echo   2. 验证安装: python check_system.py
echo ========================================
echo.
pause
