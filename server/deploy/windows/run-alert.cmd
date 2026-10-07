@echo off
rem Alerta no Telegram (uma execucao). Chamado a cada 5 minutos pela tarefa agendada "pm25-alert".
cd /d "%~dp0..\.."
if not exist data mkdir data
".venv\Scripts\python.exe" -m scripts.alert_telegram >> data\alert.log 2>&1
