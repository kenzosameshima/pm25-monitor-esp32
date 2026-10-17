@echo off
rem Backup do banco (uma execucao). Chamado todo dia as 03:15 pela tarefa agendada "pm25-backup".
rem Logs em UTF-8 (sem isso a saida redirecionada sai em cp1252, que nao tem emojis).
set PYTHONUTF8=1
cd /d "%~dp0..\.."
if not exist data mkdir data
".venv\Scripts\python.exe" -m scripts.backup >> data\backup.log 2>&1
