@echo off
rem Executa a API de ingestao e a reinicia se ela cair. Chamado pela tarefa agendada "pm25-api".
cd /d "%~dp0..\.."
if not exist data mkdir data
:loop
".venv\Scripts\python.exe" -m uvicorn app.main:app --host 0.0.0.0 --port 8000 >> data\api.log 2>&1
rem Espera 5 s antes de reiniciar (ping, porque "timeout" falha sem console).
ping -n 6 127.0.0.1 >nul
goto loop
