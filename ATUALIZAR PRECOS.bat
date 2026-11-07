@echo off
chcp 65001 >nul
cd /d "%~dp0"
set "PATH=C:\Program Files\Git\cmd;C:\Program Files\GitHub CLI;%PATH%"
set PYTHONIOENCODING=utf-8
python robo\rodar_local.py
echo.
pause
