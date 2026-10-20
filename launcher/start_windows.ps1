$ErrorActionPreference = "Stop"

$RootDir = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$ServerDir = Join-Path $RootDir "server"
$RuntimeDir = Join-Path $ServerDir "runtime"
$Python = Join-Path $ServerDir ".venv\Scripts\python.exe"
$PythonWindowless = Join-Path $ServerDir ".venv\Scripts\pythonw.exe"
$NodeDir = Join-Path $RuntimeDir "node"
$TorExe = Join-Path $RuntimeDir "tor\tor\tor.exe"
$TorDataDir = Join-Path $ServerDir "private\tor-data"
$TorGeoIp = Join-Path $RuntimeDir "tor\data\geoip"
$TorGeoIpv6 = Join-Path $RuntimeDir "tor\data\geoip6"
$LogDir = Join-Path $ServerDir "runs\logs"

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
if (-not (Test-Path $TorExe)) {
    throw "Tor local ausente. Execute novamente installer\windows\install.ps1."
}

New-Item -ItemType Directory -Force -Path $LogDir, $TorDataDir | Out-Null
$env:PATH = "$NodeDir;$env:PATH"
$env:COBRINHA_SERVER_DIR = $ServerDir
$env:PYTHONPATH = Join-Path $ServerDir "src"
$env:TTS_HOME = Join-Path $RuntimeDir "tts"
$env:COBRINHA_TOR_SOCKS_HOST = "127.0.0.1"
$env:COBRINHA_TOR_SOCKS_PORT = "9050"

if (-not (Test-LocalPort -Port 9050)) {
    Start-Process -FilePath $TorExe -WindowStyle Hidden -ArgumentList @(
        "--SocksPort", "127.0.0.1:9050",
        "--DataDirectory", "`"$TorDataDir`"",
        "--GeoIPFile", "`"$TorGeoIp`"",
        "--GeoIPv6File", "`"$TorGeoIpv6`""
    ) -RedirectStandardOutput (Join-Path $LogDir "tor.log") `
      -RedirectStandardError (Join-Path $LogDir "tor-error.log")

    for ($Attempt = 0; $Attempt -lt 120; $Attempt++) {
        if (Test-LocalPort -Port 9050) {
            break
        }
        Start-Sleep -Milliseconds 250
    }
}

if (-not (Test-LocalPort -Port 9050)) {
    throw "O Tor nao iniciou. Consulte server\runs\logs\tor-error.log"
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
        Start-Process "http://127.0.0.1:9393"
        exit 0
    } catch {
        Start-Sleep -Milliseconds 250
    }
}

throw "O servidor nao iniciou. Consulte server\runs\logs\server-error.log"
