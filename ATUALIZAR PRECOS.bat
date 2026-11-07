@echo off
chcp 65001 >nul
cd /d "%~dp0"
python robo\rodar_local.py
echo.
pause
