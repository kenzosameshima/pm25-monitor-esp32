#Requires -RunAsAdministrator
<#
Remove as tarefas agendadas e as regras de firewall criadas pelo install.ps1.
Nao mexe no banco, nos backups nem na configuracao de energia.
#>
$ErrorActionPreference = 'Continue'

foreach ($name in 'pm25-api', 'pm25-dashboard', 'pm25-alert', 'pm25-backup') {
    if (Get-ScheduledTask -TaskName $name -ErrorAction SilentlyContinue) {
        Stop-ScheduledTask -TaskName $name -ErrorAction SilentlyContinue
        Unregister-ScheduledTask -TaskName $name -Confirm:$false
        Write-Host "tarefa '$name' removida"
    }
}

# Por garantia, encerra uvicorn/streamlit que tenham sobrado (inclusive um aberto a mao).
Get-CimInstance Win32_Process -Filter "Name = 'python.exe'" |
    Where-Object { $_.CommandLine -match 'uvicorn app\.main:app|streamlit run dashboard' } |
    ForEach-Object { Stop-Process -Id $_.ProcessId -Force; Write-Host "processo $($_.ProcessId) encerrado" }

foreach ($name in 'pm25-api', 'pm25-dashboard') {
    Get-NetFirewallRule -DisplayName $name -ErrorAction SilentlyContinue | Remove-NetFirewallRule
}
Write-Host 'Pronto.'
