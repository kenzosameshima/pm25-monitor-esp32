# Servidor em Windows

Equivalente Windows dos serviços `systemd` e do `crontab` desta pasta `deploy`. Pensado para um notebook ou PC dedicado, ligado o tempo todo, na mesma rede dos nós ESP32.

## Instalação

Na máquina que será o servidor, dentro de `server`:

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements-dashboard.txt
copy .env.example .env     # defina PM25_DEVICE_TOKENS (um nó: no-01:<token de 16+ caracteres>)
```

Depois, num PowerShell **como administrador**:

```powershell
cd deploy\windows
powershell -ExecutionPolicy Bypass -File .\install.ps1
```

Se um `uvicorn` estiver aberto à mão na porta 8000, feche-o antes (Ctrl+C). O script avisa e não inicia as tarefas se a porta estiver ocupada.

## O que o `install.ps1` faz

| Item | Efeito |
|---|---|
| Validação | Confere o `.venv`, o `.env` (tokens válidos) e as dependências do dashboard |
| Energia | Desativa suspensão e hibernação (bateria e tomada) e a ação de fechar a tampa. Pule com `-SkipPower` |
| Firewall | Libera TCP 8000 nas redes Privada e Domínio. A porta 8501 (dashboard) só abre com `-OpenDashboardPort` |
| `pm25-api` | Tarefa na inicialização, como SYSTEM, sem precisar de login; reinicia a API se ela cair |
| `pm25-dashboard` | Igual, para o Streamlit (pule com `-NoDashboard`) |
| `pm25-alert` | A cada 5 minutos: alerta do Telegram |
| `pm25-backup` | Todo dia às 03:15: backup do banco |

Ao final ele imprime os IPs da máquina e testa `http://127.0.0.1:8000/health`.

## Depois de instalar

1. Reserve o IP da máquina no roteador e use-o em `API_URL` no `config.h` do firmware.
2. Deixe a rede do Windows como **Privada** (Configurações > Rede). Em rede Pública a regra do firewall não vale e o ESP32 não conecta.
3. De outro dispositivo da rede, abra `http://<ip>:8000/health`. Se responder, o ESP32 também alcança.
4. Defina `PM25_BACKUP_DIR` no `.env` como uma pasta fora do disco do servidor (pendrive ou pasta sincronizada com a nuvem).

## Operação

```powershell
Get-ScheduledTask pm25-* | Get-ScheduledTaskInfo | Select TaskName, LastRunTime, LastTaskResult
Start-ScheduledTask pm25-api       # iniciar
Stop-ScheduledTask pm25-api        # parar (o laço pode reiniciar o processo filho; use uninstall.ps1 para parar de vez)
Get-Content ..\..\data\api.log -Tail 20 -Wait
```

Logs em `server\data`: `api.log`, `dashboard.log`, `alert.log`, `backup.log`. Eles só crescem; apague ou arquive de tempos em tempos. Depois de editar o `.env`, reinicie a API:

```powershell
Stop-ScheduledTask pm25-api; Get-CimInstance Win32_Process -Filter "Name='python.exe'" | ? CommandLine -match 'uvicorn' | % { Stop-Process -Id $_.ProcessId -Force }; Start-ScheduledTask pm25-api
```

Para remover tudo (tarefas e regras de firewall; o banco e os backups ficam): `.\uninstall.ps1`.

## Cuidados que o script não resolve

- **Windows Update.** Sem ninguém logado o Windows pode reiniciar sozinho para atualizar. A API volta na inicialização, e o buffer do ESP32 (cinco dias) cobre a lacuna, mas o ideal é definir as "horas ativas" em Configurações > Windows Update para o reinício cair numa hora de pouco movimento.
- **Wi-Fi do servidor.** Prefira cabo. Se usar Wi-Fi, desative a economia de energia do adaptador (Gerenciador de Dispositivos > propriedades do adaptador > Gerenciamento de energia).
- **Python instalado só para o seu usuário.** As tarefas rodam como SYSTEM. Se a API não subir e o `api.log` reclamar de acesso ou de um Python que não encontra, reinstale o Python "para todos os usuários" (por exemplo em `C:\Python312`) e recrie o `.venv`.
- **Dashboard sem login.** Por isso a porta 8501 fica fechada por padrão. Abrir só faz sentido numa rede confiável.
- **Hora.** O banco guarda tudo em UTC; o Windows precisa estar com o relógio sincronizado (o padrão já é).
