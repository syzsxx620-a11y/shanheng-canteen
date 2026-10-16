param([switch]$Vision)
. "$PSScriptRoot\scripts\runtime.ps1"
Set-Location -LiteralPath $projectRoot
if (-not (Test-Path -LiteralPath $venvPython)) {
    & $pythonRuntime -m venv .venv
    if ($LASTEXITCODE -ne 0) { throw '创建Python环境失败' }
}
$requirementsFile = if ($Vision) { 'backend\requirements-vision.txt' } else { 'backend\requirements.txt' }
& $venvPython -m pip install -r $requirementsFile
if ($LASTEXITCODE -ne 0) { throw '后端依赖安装失败' }
& $venvPython -m backend.cli init
if ($LASTEXITCODE -ne 0) { throw '数据库初始化失败' }
& $venvPython -m backend.cli seed
if ($LASTEXITCODE -ne 0) { throw '演示数据初始化失败' }
Push-Location -LiteralPath (Join-Path $projectRoot 'frontend')
try {
    if (Test-Path -LiteralPath $pnpmRuntime) {
        & $pnpmRuntime install --frozen-lockfile
        if ($LASTEXITCODE -ne 0) { throw '前端依赖安装失败' }
    } else {
        & npm.cmd install
        if ($LASTEXITCODE -ne 0) { throw '前端依赖安装失败；请安装Node.js和npm或pnpm' }
    }
} finally { Pop-Location }
Write-Host '初始化完成。运行 .\start.ps1 启动平台。演示密码 Demo@12345。'
