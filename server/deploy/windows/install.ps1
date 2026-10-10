#Requires -RunAsAdministrator
<#
Prepara este Windows como servidor sempre ligado do sistema de coleta de PM2,5.
Equivale aos arquivos .service e ao crontab da pasta deploy, mas para Windows.

O que faz:
  - confere o ambiente virtual e o .env (e valida os tokens);
  - desativa suspensao, hibernacao e a acao de fechar a tampa (use -SkipPower para pular);
  - remove a regra de firewall da porta 8000, pois a API escuta so em 127.0.0.1 atras do tunel HTTPS
    (-OpenApiPort a libera nas redes Privada e Dominio para HTTP local, junto com PM25_API_HOST=0.0.0.0);
    a 8501 so abre com -OpenDashboardPort;
  - registra tarefas agendadas que rodam como SYSTEM, sem precisar de login:
      pm25-api        na inicializacao, reinicia se cair
      pm25-dashboard  na inicializacao, reinicia se cair (pule com -NoDashboard)
      pm25-alert      a cada 5 minutos
      pm25-backup     todo dia as 03:15

Uso (PowerShell como administrador, dentro de server\deploy\windows):
  powershell -ExecutionPolicy Bypass -File .\install.ps1
#>
param(
    [switch]$SkipPower,
    [switch]$NoDashboard,
    [switch]$OpenDashboardPort,
    [switch]$OpenApiPort
)

$ErrorActionPreference = 'Stop'
$here = $PSScriptRoot
$server = (Resolve-Path (Join-Path $here '..\..')).Path
$py = Join-Path $server '.venv\Scripts\python.exe'

function Step($msg) { Write-Host "`n== $msg" -ForegroundColor Cyan }
function Warn($msg) { Write-Host "AVISO: $msg" -ForegroundColor Yellow }

# ---------------------------------------------------------------- pre-requisitos
Step 'Conferindo ambiente'
if (-not (Test-Path $py)) {
    throw "Ambiente virtual nao encontrado em $server\.venv. Rode, dentro de server: python -m venv .venv; .venv\Scripts\python.exe -m pip install -r requirements-dashboard.txt"
}
if (-not (Test-Path (Join-Path $server '.env'))) {
    throw "Arquivo $server\.env nao encontrado. Copie .env.example para .env e defina PM25_DEVICE_TOKENS."
}
Push-Location $server
try {
    & $py -c "from app.config import get_settings; s = get_settings(); assert s.device_tokens, 'PM25_DEVICE_TOKENS vazio'; print('nos cadastrados:', ', '.join(s.device_ids))"
    if ($LASTEXITCODE -ne 0) { throw 'O .env nao passou na validacao (veja a mensagem acima).' }
    if (-not $NoDashboard) {
        & $py -c "import streamlit, pandas, altair"
        if ($LASTEXITCODE -ne 0) { throw 'Dependencias do dashboard ausentes: rode .venv\Scripts\python.exe -m pip install -r requirements-dashboard.txt' }
    }
} finally { Pop-Location }

$busy = Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue
if ($busy) {
    Warn 'a porta 8000 ja esta em uso (provavelmente um uvicorn aberto a mao). As tarefas serao registradas, mas nao iniciadas agora.'
}

# ---------------------------------------------------------------- energia
if (-not $SkipPower) {
    Step 'Desativando suspensao e hibernacao'
    powercfg /change standby-timeout-ac 0
    powercfg /change standby-timeout-dc 0
    powercfg /change hibernate-timeout-ac 0
    powercfg /change hibernate-timeout-dc 0
    # Fechar a tampa: 0 = nao fazer nada (SUB_BUTTONS / LIDACTION)
    powercfg /setacvalueindex SCHEME_CURRENT SUB_BUTTONS LIDACTION 0
    powercfg /setdcvalueindex SCHEME_CURRENT SUB_BUTTONS LIDACTION 0
    powercfg /setactive SCHEME_CURRENT
} else {
    Warn 'configuracao de energia ignorada (-SkipPower): o Windows pode suspender e parar a coleta.'
}

# ---------------------------------------------------------------- firewall
Step 'Configurando o firewall'
function Set-FirewallRule($name, $port) {
    Get-NetFirewallRule -DisplayName $name -ErrorAction SilentlyContinue | Remove-NetFirewallRule
    New-NetFirewallRule -DisplayName $name -Direction Inbound -Protocol TCP -LocalPort $port `
        -Action Allow -Profile Private, Domain | Out-Null
    Write-Host "regra '$name' (TCP $port, redes Privada e Dominio)"
}
if ($OpenApiPort) {
    Warn 'a porta 8000 fica aberta na rede local em HTTP, sem criptografia. Defina tambem PM25_API_HOST=0.0.0.0.'
    Set-FirewallRule 'pm25-api' 8000
} else {
    Get-NetFirewallRule -DisplayName 'pm25-api' -ErrorAction SilentlyContinue | Remove-NetFirewallRule
    Write-Host "porta 8000 sem regra de entrada (a API escuta so em 127.0.0.1; o acesso externo e pelo tunel HTTPS)"
}
if ($OpenDashboardPort) {
    Warn 'o dashboard nao tem login: qualquer dispositivo da rede com acesso ve os dados.'
    Set-FirewallRule 'pm25-dashboard' 8501
}
$public = Get-NetConnectionProfile | Where-Object { $_.NetworkCategory -eq 'Public' }
if ($public -and ($OpenApiPort -or $OpenDashboardPort)) {
    Warn ("a rede '{0}' esta como Publica; a regra nao vale nela e o ESP32 nao vai conectar. Mude para Privada em Configuracoes > Rede." -f ($public.Name -join ', '))
}

# ---------------------------------------------------------------- tarefas agendadas
Step 'Registrando tarefas agendadas'
$principal = New-ScheduledTaskPrincipal -UserId 'SYSTEM' -LogonType ServiceAccount -RunLevel Highest

function Register-Pm25Task($name, $cmd, $trigger, $description, [switch]$KeepAlive) {
    $action = New-ScheduledTaskAction -Execute (Join-Path $here $cmd) -WorkingDirectory $server
    $settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
        -StartWhenAvailable -MultipleInstances IgnoreNew -ExecutionTimeLimit ([TimeSpan]::Zero)
    if ($KeepAlive) {
        $settings.RestartCount = 999
        $settings.RestartInterval = 'PT1M'
    }
    Register-ScheduledTask -TaskName $name -Action $action -Trigger $trigger -Principal $principal `
        -Settings $settings -Description $description -Force | Out-Null
    Write-Host "tarefa '$name' registrada"
}

Register-Pm25Task 'pm25-api' 'run-api.cmd' (New-ScheduledTaskTrigger -AtStartup) `
    'PM2.5 - API de ingestao (porta 8000)' -KeepAlive

if (-not $NoDashboard) {
    Register-Pm25Task 'pm25-dashboard' 'run-dashboard.cmd' (New-ScheduledTaskTrigger -AtStartup) `
        'PM2.5 - dashboard Streamlit (porta 8501)' -KeepAlive
}

$every5 = New-ScheduledTaskTrigger -Once -At (Get-Date).Date -RepetitionInterval (New-TimeSpan -Minutes 5) `
    -RepetitionDuration (New-TimeSpan -Days 3650)
Register-Pm25Task 'pm25-alert' 'run-alert.cmd' $every5 'PM2.5 - alerta no Telegram a cada 5 minutos'

Register-Pm25Task 'pm25-backup' 'run-backup.cmd' (New-ScheduledTaskTrigger -Daily -At '03:15') `
    'PM2.5 - backup diario do banco'

# ---------------------------------------------------------------- iniciar agora
if (-not $busy) {
    Step 'Iniciando'
    Start-ScheduledTask -TaskName 'pm25-api'
    if (-not $NoDashboard) { Start-ScheduledTask -TaskName 'pm25-dashboard' }
    $ok = $false
    foreach ($i in 1..15) {
        Start-Sleep -Seconds 2
        try {
            $r = Invoke-WebRequest -Uri 'http://127.0.0.1:8000/health' -UseBasicParsing -TimeoutSec 3
            if ($r.StatusCode -eq 200) { $ok = $true; break }
        } catch { }
    }
    if ($ok) { Write-Host 'API respondendo em /health' -ForegroundColor Green }
    else { Warn "a API nao respondeu em 30 s; veja $server\data\api.log" }
}

Step 'Pronto'
$ips = Get-NetIPAddress -AddressFamily IPv4 |
    Where-Object { $_.IPAddress -notlike '127.*' -and $_.IPAddress -notlike '169.254.*' } |
    Select-Object -ExpandProperty IPAddress
if ($OpenApiPort) {
    Write-Host ("IPs desta maquina: {0}" -f ($ips -join ', '))
    Write-Host 'Alternativa HTTP local: API_URL "http://<um desses IPs>:8000/v1/measurements" e reserve o IP no roteador.'
} else {
    Write-Host 'API em http://127.0.0.1:8000, so nesta maquina. Publique-a pelo tunel HTTPS (secao "Transporte HTTPS entre redes" do README).'
}
Write-Host "Logs em $server\data (api.log, dashboard.log, alert.log, backup.log)."
