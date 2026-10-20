param(
    [switch]$AcceptCoquiLicense,
    [switch]$SkipTtsModel
)

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"

$RootDir = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$ServerDir = Join-Path $RootDir "server"
$MonitorDir = Join-Path $ServerDir "external\tiktok-live-monitoring-server"
$RuntimeDir = Join-Path $ServerDir "runtime"
$PythonRuntime = Join-Path $RuntimeDir "python"
$NodeRuntime = Join-Path $RuntimeDir "node"
$TorRuntime = Join-Path $RuntimeDir "tor"
$DownloadDir = Join-Path ([IO.Path]::GetTempPath()) "SnakeReyersInstaller"

$PythonUrl = "https://www.python.org/ftp/python/3.12.10/python-3.12.10-amd64.exe"
$PythonSha256 = "67b5635e80ea51072b87941312d00ec8927c4db9ba18938f7ad2d27b328b95fb"
$NodeUrl = "https://nodejs.org/dist/v22.23.3/node-v22.23.3-win-x64.zip"
$NodeSha256 = "2b0ff57b049cda1bbcea2240eec20467018713c1efe1f7360c2681859b90ed71"
$TorUrl = "https://dist.torproject.org/torbrowser/15.0.25/tor-expert-bundle-windows-x86_64-15.0.25.tar.gz"
$TorSha256 = "c1988c701de2f24f7d098d1d6d7f507b58f27740d097f29c246e0524d639b252"

function Get-VerifiedDownload {
    param(
        [Parameter(Mandatory = $true)][string]$Url,
        [Parameter(Mandatory = $true)][string]$Destination,
        [Parameter(Mandatory = $true)][string]$Sha256
    )

    if (Test-Path $Destination) {
        $ExistingHash = (Get-FileHash -Algorithm SHA256 -Path $Destination).Hash.ToLowerInvariant()
        if ($ExistingHash -eq $Sha256) {
            return
        }
        Remove-Item -Force $Destination
    }

    Write-Host "Baixando $([IO.Path]::GetFileName($Destination))..."
    Invoke-WebRequest -UseBasicParsing -Uri $Url -OutFile $Destination
    $ActualHash = (Get-FileHash -Algorithm SHA256 -Path $Destination).Hash.ToLowerInvariant()
    if ($ActualHash -ne $Sha256) {
        Remove-Item -Force $Destination
        throw "Falha de integridade no download de $Url"
    }
}

function Invoke-PipInstall {
    param([Parameter(Mandatory = $true)][string[]]$Arguments)

    & $Python -m pip install --disable-pip-version-check @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "Falha ao instalar dependencias Python: $($Arguments -join ' ')"
    }
}

function Install-AudioPackages {
    $ManifestPath = Join-Path $ServerDir "assets\audio-manifest.json"
    if (-not (Test-Path $ManifestPath)) {
        throw "Manifesto dos pacotes de audio ausente: $ManifestPath"
    }

    $ManifestHash = (Get-FileHash -Algorithm SHA256 -Path $ManifestPath).Hash.ToLowerInvariant()
    $MarkerPath = Join-Path $ServerDir "assets\.audio-package-version"
    if (
        (Test-Path $MarkerPath) -and
        ((Get-Content -Raw $MarkerPath).Trim() -eq $ManifestHash)
    ) {
        Write-Host "Vozes e musicas ja estao instaladas."
        return
    }

    $Manifest = Get-Content -Raw $ManifestPath | ConvertFrom-Json
    foreach ($Pack in $Manifest.packs) {
        $PackName = [string]$Pack.name
        $PackHash = ([string]$Pack.sha256).ToLowerInvariant()
        $Candidates = @(
            (Join-Path (Split-Path $RootDir -Parent) $PackName),
            (Join-Path $RootDir $PackName),
            (Join-Path (Join-Path $RootDir "packages") $PackName)
        )
        $Archive = $Candidates | Where-Object { Test-Path $_ } | Select-Object -First 1

        if (-not $Archive) {
            $Archive = Join-Path $DownloadDir $PackName
            Get-VerifiedDownload -Url ([string]$Pack.url) -Destination $Archive -Sha256 $PackHash
        } else {
            $ActualHash = (Get-FileHash -Algorithm SHA256 -Path $Archive).Hash.ToLowerInvariant()
            if ($ActualHash -ne $PackHash) {
                throw "Pacote de audio local invalido: $Archive"
            }
        }

        Write-Host "Instalando $PackName..."
        Expand-Archive -Force -Path $Archive -DestinationPath $RootDir
    }

    Set-Content -Encoding ASCII -NoNewline -Path $MarkerPath -Value $ManifestHash
}

[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
New-Item -ItemType Directory -Force -Path $RuntimeDir, $DownloadDir | Out-Null

$PythonExe = Join-Path $PythonRuntime "python.exe"
if (-not (Test-Path $PythonExe)) {
    $PythonInstaller = Join-Path $DownloadDir "python-3.12.10-amd64.exe"
    Get-VerifiedDownload -Url $PythonUrl -Destination $PythonInstaller -Sha256 $PythonSha256
    New-Item -ItemType Directory -Force -Path $PythonRuntime | Out-Null
    $PythonInstall = Start-Process -Wait -PassThru -FilePath $PythonInstaller -ArgumentList @(
        "/quiet",
        "InstallAllUsers=0",
        "Include_launcher=0",
        "Include_test=0",
        "Include_doc=0",
        "Include_tcltk=0",
        "Include_pip=1",
        "PrependPath=0",
        "TargetDir=`"$PythonRuntime`""
    )
    if ($PythonInstall.ExitCode -ne 0 -or -not (Test-Path $PythonExe)) {
        throw "Nao foi possivel instalar o Python portatil. Codigo: $($PythonInstall.ExitCode)"
    }
}

$NodeExe = Join-Path $NodeRuntime "node.exe"
if (-not (Test-Path $NodeExe)) {
    $NodeArchive = Join-Path $DownloadDir "node-v22.23.3-win-x64.zip"
    $NodeExtract = Join-Path $DownloadDir "node"
    Get-VerifiedDownload -Url $NodeUrl -Destination $NodeArchive -Sha256 $NodeSha256
    if (Test-Path $NodeExtract) {
        Remove-Item -Recurse -Force $NodeExtract
    }
    if (Test-Path $NodeRuntime) {
        Remove-Item -Recurse -Force $NodeRuntime
    }
    Expand-Archive -Force -Path $NodeArchive -DestinationPath $NodeExtract
    $NodeSource = Get-ChildItem -Directory $NodeExtract | Select-Object -First 1
    if (-not $NodeSource) {
        throw "Pacote do Node.js sem diretorio principal."
    }
    New-Item -ItemType Directory -Force -Path $NodeRuntime | Out-Null
    Copy-Item -Recurse -Force -Path (Join-Path $NodeSource.FullName "*") -Destination $NodeRuntime
}

$TorExe = Join-Path $TorRuntime "tor\tor.exe"
if (-not (Test-Path $TorExe)) {
    $TorArchive = Join-Path $DownloadDir "tor-expert-bundle-windows-x86_64-15.0.25.tar.gz"
    Get-VerifiedDownload -Url $TorUrl -Destination $TorArchive -Sha256 $TorSha256
    if (Test-Path $TorRuntime) {
        Remove-Item -Recurse -Force $TorRuntime
    }
    New-Item -ItemType Directory -Force -Path $TorRuntime | Out-Null
    & tar -xzf $TorArchive -C $TorRuntime
    if ($LASTEXITCODE -ne 0 -or -not (Test-Path $TorExe)) {
        throw "Nao foi possivel extrair o Tor Expert Bundle."
    }
}

$NodeMajor = [int](& $NodeExe -p "Number(process.versions.node.split('.')[0])")
if ($NodeMajor -lt 22) {
    throw "O Node.js local precisa ser versao 22 ou superior."
}

$VenvDir = Join-Path $ServerDir ".venv"
$Python = Join-Path $VenvDir "Scripts\python.exe"
if (-not (Test-Path $Python)) {
    & $PythonExe -m venv $VenvDir
}

Invoke-PipInstall -Arguments @("--upgrade", "pip")
Invoke-PipInstall -Arguments @("-r", (Join-Path $ServerDir "requirements.txt"))

Write-Host "Instalando o mecanismo XTTS..."
& $Python -m pip install --disable-pip-version-check `
    --index-url "https://download.pytorch.org/whl/cu126" `
    "torch==2.7.1" "torchaudio==2.7.1"
if ($LASTEXITCODE -ne 0) {
    Write-Warning "CUDA nao ficou disponivel; instalando o modo CPU do TTS."
    Invoke-PipInstall -Arguments @(
        "--index-url", "https://download.pytorch.org/whl/cpu",
        "torch==2.7.1", "torchaudio==2.7.1"
    )
}
Invoke-PipInstall -Arguments @("-r", (Join-Path $ServerDir "requirements-voice.txt"))

$env:TTS_HOME = Join-Path $RuntimeDir "tts"
$TtsModelFile = Join-Path $env:TTS_HOME "tts\tts_models--multilingual--multi-dataset--xtts_v2\model.pth"
if (-not $SkipTtsModel -and -not (Test-Path $TtsModelFile)) {
    if (-not $AcceptCoquiLicense) {
        Write-Host "O XTTS usa a licenca Coqui Public Model License (CPML)."
        $Answer = Read-Host "Voce aceita a CPML para baixar o modelo XTTS agora? [S/N]"
        if ($Answer -notmatch "^[SsYy]") {
            throw "A instalacao completa exige aceitar a licenca do modelo XTTS."
        }
    }
    $env:COQUI_TOS_AGREED = "1"
    & $Python (Join-Path $ServerDir "scripts\prepare_tts_model.py")
    if ($LASTEXITCODE -ne 0) {
        throw "Nao foi possivel preparar o modelo XTTS."
    }
} elseif (Test-Path $TtsModelFile) {
    Write-Host "Modelo XTTS ja esta preparado."
}

Install-AudioPackages

$env:PATH = "$NodeRuntime;$env:PATH"
$Npm = Join-Path $NodeRuntime "npm.cmd"
Push-Location $MonitorDir
try {
    & $Npm ci --omit=dev
    if ($LASTEXITCODE -ne 0) {
        throw "Falha ao instalar as dependencias do monitor TikTok."
    }
} finally {
    Pop-Location
}

New-Item -ItemType Directory -Force -Path `
    (Join-Path $ServerDir "private"), `
    (Join-Path $ServerDir "runs\logs") | Out-Null

if (Test-Path $DownloadDir) {
    Remove-Item -Recurse -Force $DownloadDir
}

Write-Host "Snake Reyers instalado com TTS, vozes, musicas, Python, Node.js e Tor locais."
Write-Host "Execute launcher\start_windows.ps1"
