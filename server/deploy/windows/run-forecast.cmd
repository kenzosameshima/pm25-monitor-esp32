@echo off
rem Previsao horaria (uma execucao). Chamado a cada hora, aos 5 minutos, pela tarefa agendada "pm25-forecast".
cd /d "%~dp0..\.."
if not exist data mkdir data
".venv\Scripts\python.exe" -m scripts.forecast_job >> data\forecast.log 2>&1
