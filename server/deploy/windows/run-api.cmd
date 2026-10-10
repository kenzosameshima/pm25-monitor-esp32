@echo off
rem Executa a API de ingestao e a reinicia se ela cair. Chamado pela tarefa agendada "pm25-api".
rem Escuta so em 127.0.0.1: o tunel termina o TLS e encaminha. --proxy-headers registra o IP real do cliente
rem (X-Forwarded-For, aceito so de 127.0.0.1). Para HTTP na rede local: PM25_API_HOST=0.0.0.0 e install.ps1 -OpenApiPort.
if not defined PM25_API_HOST set PM25_API_HOST=127.0.0.1
cd /d "%~dp0..\.."
if not exist data mkdir data
:loop
".venv\Scripts\python.exe" -m uvicorn app.main:app --host %PM25_API_HOST% --port 8000 --proxy-headers --forwarded-allow-ips 127.0.0.1 >> data\api.log 2>&1
rem Espera 5 s antes de reiniciar (ping, porque "timeout" falha sem console).
ping -n 6 127.0.0.1 >nul
goto loop
