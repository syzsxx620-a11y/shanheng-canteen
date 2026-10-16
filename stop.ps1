. "$PSScriptRoot\scripts\runtime.ps1"
$pidFile = Join-Path $projectRoot 'data\services.json'
if (-not (Test-Path -LiteralPath $pidFile)) { Write-Host '没有由启动脚本记录的服务。'; exit }
foreach ($serviceRecord in @(Get-Content -LiteralPath $pidFile -Raw | ConvertFrom-Json)) {
    $serviceProcess = Get-Process -Id $serviceRecord.id -ErrorAction SilentlyContinue
    if ($serviceProcess -and $serviceProcess.StartTime.ToUniversalTime().Ticks.ToString() -eq $serviceRecord.started_ticks) {
        & taskkill.exe /PID $serviceProcess.Id /T /F | Out-Null
        if ($LASTEXITCODE -ne 0) { throw '停止服务失败，请在创建服务的同一用户终端执行；已保留进程记录。' }
    }
}
Remove-Item -LiteralPath $pidFile
Write-Host '本项目服务已停止。'
