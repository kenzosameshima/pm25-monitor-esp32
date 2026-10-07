@echo off
rem Backup do banco (uma execucao). Chamado todo dia as 03:15 pela tarefa agendada "pm25-backup".
cd /d "%~dp0..\.."
if not exist data mkdir data
".venv\Scripts\python.exe" -m scripts.backup >> data\backup.log 2>&1
