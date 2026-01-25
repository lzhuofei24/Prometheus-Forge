@echo off
echo ========================================
echo Prometheus Forge 前端启动脚本
echo ========================================
echo.

cd /d %~dp0..\web

if not exist node_modules (
    echo 检测到未安装依赖，正在安装...
    call npm install
)

echo 启动前端开发服务器...
start "Prometheus Forge Frontend" cmd /k "npm run dev"

echo.
echo ========================================
echo 前端服务器已启动
echo 访问: http://localhost:5173
echo ========================================
echo.
pause
