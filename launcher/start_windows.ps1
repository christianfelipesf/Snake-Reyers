$ErrorActionPreference = "Stop"

$RootDir = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$ServerDir = Join-Path $RootDir "server"
$RuntimeDir = Join-Path $ServerDir "runtime"
$Python = Join-Path $ServerDir ".venv\Scripts\python.exe"
$PythonWindowless = Join-Path $ServerDir ".venv\Scripts\pythonw.exe"
$NodeDir = Join-Path $RuntimeDir "node"
$LogDir = Join-Path $ServerDir "runs\logs"
$ShortcutInstaller = Join-Path $RootDir "launcher\create_shortcut.ps1"

if (Test-Path $ShortcutInstaller -PathType Leaf) {
    try {
        & $ShortcutInstaller -InstallRoot $RootDir | Out-Null
    } catch {
        Write-Warning "Nao foi possivel reparar o atalho: $($_.Exception.Message)"
    }
}

function Test-LocalPort {
    param([int]$Port)
    $Client = New-Object System.Net.Sockets.TcpClient
    try {
        $Result = $Client.BeginConnect("127.0.0.1", $Port, $null, $null)
        if (-not $Result.AsyncWaitHandle.WaitOne(400)) {
            return $false
        }
        $Client.EndConnect($Result)
        return $true
    } catch {
        return $false
    } finally {
        $Client.Close()
    }
}

if (
    -not (Test-Path $Python) -or
    -not (Test-Path $PythonWindowless) -or
    -not (Test-Path (Join-Path $NodeDir "node.exe"))
) {
    throw "Execute installer\windows\install.ps1 primeiro."
}
$RequiredPayload = @(
    (Join-Path $RootDir "game\windows\SnakeReyers.exe"),
    (Join-Path $ServerDir "assets\audio-manifest.json"),
    (Join-Path $ServerDir "assets\.audio-package-version")
)
$MissingPayload = @(
    $RequiredPayload | Where-Object { -not (Test-Path $_ -PathType Leaf) }
)
if ($MissingPayload.Count -gt 0) {
    throw "Instalacao incompleta. Execute novamente installer\windows\install.ps1."
}

New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
$env:PATH = "$NodeDir;$env:PATH"
$env:COBRINHA_SERVER_DIR = $ServerDir
$env:PYTHONPATH = Join-Path $ServerDir "src"

if (Test-LocalPort -Port 9393) {
    try {
        Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:9393/api/health" -TimeoutSec 2 | Out-Null
        if ($env:SNAKE_REYERS_SKIP_BROWSER -ne "1") {
            Start-Process "http://127.0.0.1:9393"
        }
        exit 0
    } catch {
        throw "A porta 9393 esta ocupada por outro programa."
    }
}

& $Python (Join-Path $RootDir "launcher\update.py") --install
if ($LASTEXITCODE -ne 0) {
    Write-Warning "Nao foi possivel atualizar agora; iniciando a versao instalada."
}

Start-Process -FilePath $PythonWindowless `
    -ArgumentList "-m", "uvicorn", "cobrinha_server.main:app", "--host", "127.0.0.1", "--port", "9393" `
    -WorkingDirectory $ServerDir `
    -RedirectStandardOutput (Join-Path $LogDir "server.log") `
    -RedirectStandardError (Join-Path $LogDir "server-error.log")

for ($Attempt = 0; $Attempt -lt 60; $Attempt++) {
    try {
        Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:9393/api/health" | Out-Null
        if ($env:SNAKE_REYERS_SKIP_BROWSER -ne "1") {
            Start-Process "http://127.0.0.1:9393"
        }
        exit 0
    } catch {
        Start-Sleep -Milliseconds 250
    }
}

throw "O servidor nao iniciou. Consulte server\runs\logs\server-error.log"
