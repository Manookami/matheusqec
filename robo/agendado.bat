@echo off
rem Rodado pelo Agendador de Tarefas do Windows todo dia (sem "pause"); o resultado fica em robo\ultimo_log.txt
cd /d "%~dp0.."
set "PATH=C:\Program Files\Git\cmd;C:\Program Files\GitHub CLI;%PATH%"
set PYTHONIOENCODING=utf-8
echo ===== %date% %time% > robo\ultimo_log.txt
python robo\rodar_local.py >> robo\ultimo_log.txt 2>&1
