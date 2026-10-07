@echo off
rem Executa o dashboard Streamlit e o reinicia se ele cair. Chamado pela tarefa agendada "pm25-dashboard".
cd /d "%~dp0..\.."
if not exist data mkdir data
:loop
".venv\Scripts\python.exe" -m streamlit run dashboard/app.py --server.headless true --server.port 8501 --browser.gatherUsageStats false >> data\dashboard.log 2>&1
ping -n 6 127.0.0.1 >nul
goto loop
