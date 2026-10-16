. "$PSScriptRoot\scripts\runtime.ps1"
Set-Location -LiteralPath $projectRoot
if (-not (Test-Path -LiteralPath $venvPython)) { throw '请先运行 .\setup.ps1' }
$processDir = Join-Path $projectRoot 'data'
New-Item -ItemType Directory -Path $processDir -Force | Out-Null
$pidFile = Join-Path $processDir 'services.json'
if (Test-Path -LiteralPath $pidFile) { throw '存在服务记录，请先运行 .\stop.ps1 再启动' }
foreach ($servicePort in @(8000,5173)) {
    $probe = New-Object System.Net.Sockets.TcpClient
    try {
        $probe.Connect('127.0.0.1',$servicePort)
        throw "端口 $servicePort 已被占用，请先停止占用该端口的服务。"
    } catch [System.Net.Sockets.SocketException] {
        # 连接被拒绝表示端口空闲。
    } finally { $probe.Dispose() }
}
$started = @()
try {
    $apiProcess = Start-Process -FilePath $venvPython -ArgumentList '-m uvicorn backend.main:app --host 127.0.0.1 --port 8000' -WorkingDirectory $projectRoot -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $processDir 'api.log') -RedirectStandardError (Join-Path $processDir 'api-error.log')
    $started += $apiProcess
    $workerProcess = Start-Process -FilePath $venvPython -ArgumentList '-m backend.worker' -WorkingDirectory $projectRoot -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $processDir 'worker.log') -RedirectStandardError (Join-Path $processDir 'worker-error.log')
    $started += $workerProcess
    $vitePath = Join-Path $projectRoot 'frontend\node_modules\vite\bin\vite.js'
    $uiProcess = Start-Process -FilePath $nodeRuntime -ArgumentList @(('"' + $vitePath + '"'), '--host 127.0.0.1 --port 5173 --strictPort') -WorkingDirectory (Join-Path $projectRoot 'frontend') -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $processDir 'frontend.log') -RedirectStandardError (Join-Path $processDir 'frontend-error.log')
    $started += $uiProcess
    $started | ForEach-Object { @{ id = $_.Id; started_ticks = $_.StartTime.ToUniversalTime().Ticks.ToString() } } | ConvertTo-Json | Set-Content -LiteralPath $pidFile -Encoding utf8
    Start-Sleep -Seconds 2
    if ($started | Where-Object { $_.HasExited }) { throw '服务启动失败，请检查data目录日志' }
    Write-Host '平台 http://127.0.0.1:5173  |  API文档 http://127.0.0.1:8000/docs'
    Write-Host '演示账号 student / manager / admin，密码 Demo@12345。停止服务：.\stop.ps1'
} catch {
    foreach ($ownedProcess in $started) {
        if (-not $ownedProcess.HasExited) { & taskkill.exe /PID $ownedProcess.Id /T /F | Out-Null }
    }
    if (Test-Path -LiteralPath $pidFile) { Remove-Item -LiteralPath $pidFile }
    throw
}
