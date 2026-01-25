@echo off
chcp 65001 >nul
echo ========================================
echo Prometheus Forge - Restart All Services
echo ========================================
echo.

echo Step 1: Stopping all services...
call stop_all.bat

timeout /t 3 /nobreak >nul

echo.
echo Step 2: Starting all services...
call start_all.bat
