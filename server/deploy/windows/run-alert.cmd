@echo off
rem Alerta no Telegram (uma execucao). Chamado a cada 5 minutos pela tarefa agendada "pm25-alert".
rem Logs em UTF-8 (sem isso a saida redirecionada sai em cp1252, que nao tem emojis).
set PYTHONUTF8=1
cd /d "%~dp0..\.."
if not exist data mkdir data
".venv\Scripts\python.exe" -m scripts.alert_telegram >> data\alert.log 2>&1
