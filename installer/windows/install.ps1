param(
    [switch]$SkipTtsModel,
    [switch]$RepairDistributionOnly
)

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"

$RootDir = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$ServerDir = Join-Path $RootDir "server"
$MonitorDir = Join-Path $ServerDir "external\tiktok-live-monitoring-server"
$RuntimeDir = Join-Path $ServerDir "runtime"
$PythonRuntime = Join-Path $RuntimeDir "python"
$NodeRuntime = Join-Path $RuntimeDir "node"
$DownloadDir = Join-Path ([IO.Path]::GetTempPath()) "SnakeReyersInstaller"

$PythonUrl = "https://www.python.org/ftp/python/3.12.10/python-3.12.10-amd64.exe"
$PythonSha256 = "67b5635e80ea51072b87941312d00ec8927c4db9ba18938f7ad2d27b328b95fb"
$NodeUrl = "https://nodejs.org/dist/v22.23.3/node-v22.23.3-win-x64.zip"
$NodeSha256 = "2b0ff57b049cda1bbcea2240eec20467018713c1efe1f7360c2681859b90ed71"
$DefaultUpdateManifestUrl = "https://raw.githubusercontent.com/golgol2/Snake-Reyers/main/update-manifest.json"

function Get-VerifiedDownload {
    param(
        [Parameter(Mandatory = $true)][string]$Url,
        [Parameter(Mandatory = $true)][string]$Destination,
        [Parameter(Mandatory = $true)][string]$Sha256
    )

    New-Item -ItemType Directory -Force -Path (Split-Path $Destination -Parent) | Out-Null
    if (Test-Path $Destination) {
        $ExistingHash = (Get-FileHash -Algorithm SHA256 -Path $Destination).Hash.ToLowerInvariant()
        if ($ExistingHash -eq $Sha256) {
            return
        }
        Remove-Item -Force $Destination
    }

    $Temporary = "$Destination.download"
    $Curl = Get-Command "curl.exe" -ErrorAction SilentlyContinue
    for ($Attempt = 1; $Attempt -le 4; $Attempt++) {
        if (Test-Path $Temporary) {
            Remove-Item -Force $Temporary
        }

        try {
            Write-Host "Baixando $([IO.Path]::GetFileName($Destination)) (tentativa $Attempt de 4)..."
            if ($Curl) {
                & $Curl.Source `
                    --fail `
                    --location `
                    --silent `
                    --show-error `
                    --connect-timeout 30 `
                    --max-time 1800 `
                    --retry 2 `
                    --retry-delay 2 `
                    --output $Temporary `
                    $Url
                if ($LASTEXITCODE -ne 0) {
                    throw "curl.exe terminou com o codigo $LASTEXITCODE"
                }
            } else {
                Invoke-WebRequest -UseBasicParsing -Uri $Url -OutFile $Temporary
            }

            if (-not (Test-Path $Temporary) -or (Get-Item $Temporary).Length -le 0) {
                throw "O servidor nao enviou dados."
            }
            $ActualHash = (Get-FileHash -Algorithm SHA256 -Path $Temporary).Hash.ToLowerInvariant()
            if ($ActualHash -ne $Sha256) {
                throw "O SHA-256 recebido nao confere."
            }

            Move-Item -Force -Path $Temporary -Destination $Destination
            return
        } catch {
            if (Test-Path $Temporary) {
                Remove-Item -Force $Temporary
            }
            if ($Attempt -eq 4) {
                throw "Falha ao baixar ou validar $Url depois de 4 tentativas: $($_.Exception.Message)"
            }
            Write-Warning "Download interrompido. Nova tentativa sera feita automaticamente."
            Start-Sleep -Seconds (3 * $Attempt)
        }
    }
}

function Compare-Version {
    param(
        [string]$Published,
        [string]$Installed
    )

    $PublishedVersion = $null
    $InstalledVersion = $null
    if (-not [System.Version]::TryParse(([string]$Published).Trim().TrimStart([char[]]"vV"), [ref]$PublishedVersion)) {
        return 0
    }
    if (-not [System.Version]::TryParse(([string]$Installed).Trim().TrimStart([char[]]"vV"), [ref]$InstalledVersion)) {
        return 0
    }
    return $PublishedVersion.CompareTo($InstalledVersion)
}

function Test-Python312 {
    param([string]$Executable)

    if (-not $Executable -or -not (Test-Path $Executable -PathType Leaf)) {
        return $false
    }

    try {
        $Version = & $Executable -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>$null
        return (
            $LASTEXITCODE -eq 0 -and
            ([string]$Version).Trim() -eq "3.12"
        )
    } catch {
        return $false
    }
}

function Find-Python312 {
    $Candidates = [System.Collections.Generic.List[string]]::new()
    $RegistryKeys = @(
        "HKCU:\Software\Python\PythonCore\3.12\InstallPath",
        "HKLM:\Software\Python\PythonCore\3.12\InstallPath",
        "HKLM:\Software\WOW6432Node\Python\PythonCore\3.12\InstallPath"
    )
    foreach ($Key in $RegistryKeys) {
        if (Test-Path $Key) {
            $Value = [string](Get-ItemProperty -Path $Key -ErrorAction SilentlyContinue).'(default)'
            if ($Value) {
                $Candidates.Add($Value)
            }
        }
    }
    if ($env:LocalAppData) {
        $Candidates.Add((Join-Path $env:LocalAppData "Programs\Python\Python312"))
    }
    if ($env:ProgramFiles) {
        $Candidates.Add((Join-Path $env:ProgramFiles "Python312"))
    }

    foreach ($Candidate in $Candidates) {
        $Executable = Join-Path ([string]$Candidate).TrimEnd([char]'\', [char]'/') "python.exe"
        if (Test-Python312 $Executable) {
            return $Executable
        }
    }
    return $null
}

function Repair-DistributionPayload {
    $RequiredFiles = @(
        (Join-Path $RootDir "game\windows\SnakeReyers.exe"),
        (Join-Path $ServerDir "assets\audio-manifest.json")
    )
    $MissingFiles = @(
        $RequiredFiles | Where-Object { -not (Test-Path $_ -PathType Leaf) }
    )
    if ($MissingFiles.Count -eq 0) {
        return
    }

    Write-Warning "O pacote baixado esta incompleto (normalmente Code > Download ZIP)."
    Write-Host "Baixando o pacote oficial completo do Snake Reyers Lite..."

    $ManifestUrl = if ($env:SNAKE_REYERS_UPDATE_MANIFEST_URL) {
        $env:SNAKE_REYERS_UPDATE_MANIFEST_URL
    } else {
        $DefaultUpdateManifestUrl
    }
    if (-not $ManifestUrl.StartsWith("https://")) {
        throw "O manifesto oficial precisa usar HTTPS: $ManifestUrl"
    }

    $BootstrapDir = Join-Path $DownloadDir "distribution-repair"
    $ManifestPath = Join-Path $BootstrapDir "update-manifest.json"
    $ExtractDir = Join-Path $BootstrapDir "extracted"
    New-Item -ItemType Directory -Force -Path $BootstrapDir | Out-Null
    Invoke-WebRequest -UseBasicParsing -Uri $ManifestUrl -OutFile $ManifestPath
    $Manifest = Get-Content -Raw $ManifestPath | ConvertFrom-Json

    $LocalVersionFile = Join-Path $RootDir "VERSION"
    $LocalVersion = if (Test-Path $LocalVersionFile -PathType Leaf) {
        (Get-Content -Raw $LocalVersionFile).Trim()
    } else {
        "0.0.0"
    }
    $PublishedVersion = [string]$Manifest.version
    if ((Compare-Version -Published $PublishedVersion -Installed $LocalVersion) -lt 0) {
        Write-Warning "A versao publicada ($PublishedVersion) e mais antiga que a que esta instalada aqui ($LocalVersion)."
        Write-Warning "Para nao rebaixar o seu Snake Reyers Lite, o pacote oficial nao sera aplicado por cima desta pasta."
        Write-Warning "Publique uma release $LocalVersion (com o jogo compilado e o audio-manifest.json) ou coloque esses arquivos manualmente."
        return
    }

    $Package = $Manifest.packages.'windows-x86_64'
    if (-not $Package) {
        throw "O manifesto oficial nao possui um pacote para Windows x64."
    }

    $PackageUrl = [string]$Package.url
    $PackageHash = ([string]$Package.sha256).ToLowerInvariant()
    if (
        -not $PackageUrl.StartsWith("https://") -or
        $PackageHash -notmatch "^[0-9a-f]{64}$"
    ) {
        throw "Os dados do pacote Windows no manifesto oficial sao invalidos."
    }

    $Archive = Join-Path $BootstrapDir "SnakeReyers-Windows-x64.zip"
    Get-VerifiedDownload -Url $PackageUrl -Destination $Archive -Sha256 $PackageHash
    if (Test-Path $ExtractDir) {
        Remove-Item -Recurse -Force $ExtractDir
    }
    Expand-Archive -Force -Path $Archive -DestinationPath $ExtractDir

    $SourceRoot = Join-Path $ExtractDir "SnakeReyers"
    $SourceGame = Join-Path $SourceRoot "game\windows\SnakeReyers.exe"
    $SourceAudioManifest = Join-Path $SourceRoot "server\assets\audio-manifest.json"
    if (
        -not (Test-Path $SourceGame -PathType Leaf) -or
        -not (Test-Path $SourceAudioManifest -PathType Leaf)
    ) {
        throw "O pacote oficial nao contem todos os arquivos obrigatorios."
    }

    Get-ChildItem -Path $SourceRoot -Recurse -File -Force | ForEach-Object {
        $RelativePath = $_.FullName.Substring($SourceRoot.Length).TrimStart([char]'\')
        $Destination = Join-Path $RootDir $RelativePath
        New-Item -ItemType Directory -Force -Path (Split-Path $Destination -Parent) | Out-Null
        Copy-Item -Force -Path $_.FullName -Destination $Destination
    }

    $StillMissing = @(
        $RequiredFiles | Where-Object { -not (Test-Path $_ -PathType Leaf) }
    )
    if ($StillMissing.Count -gt 0) {
        throw "Nao foi possivel reparar o pacote incompleto: $($StillMissing -join ', ')"
    }

    Write-Host "Pacote oficial recuperado e validado com sucesso."
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
        Write-Warning "Manifesto dos pacotes de audio ausente: $ManifestPath"
        Write-Warning "As musicas de fundo e as vozes compartilhadas nao serao instaladas agora."
        Write-Warning "Elas chegam quando existir uma release compativel ou quando o arquivo for colocado manualmente."
        return
    }

    $ManifestHash = (Get-FileHash -Algorithm SHA256 -Path $ManifestPath).Hash.ToLowerInvariant()
    $MarkerPath = Join-Path $ServerDir "assets\.audio-package-version"
    $BackgroundReady = @(
        Get-ChildItem -Path (Join-Path $ServerDir "assets\music\background") -File -ErrorAction SilentlyContinue
    ).Count -gt 0
    $VoiceReady = @(
        Get-ChildItem -Path (Join-Path $ServerDir "assets\voice\piper") -Filter "*.onnx" -File -ErrorAction SilentlyContinue
    ).Count -gt 0

    if (
        (Test-Path $MarkerPath) -and
        ((Get-Content -Raw $MarkerPath).Trim() -eq $ManifestHash) -and
        $BackgroundReady -and
        $VoiceReady
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

$env:COBRINHA_SERVER_DIR = $ServerDir
$env:PYTHONPATH = Join-Path $ServerDir "src"

Repair-DistributionPayload
if ($RepairDistributionOnly) {
    Write-Host "Arquivos obrigatorios da distribuicao estao prontos."
    exit 0
}

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
    if (
        $PythonInstall.ExitCode -ne 0 -or
        -not (Test-Path $PythonExe)
    ) {
        $FallbackPython = Find-Python312
        if ($FallbackPython) {
            $FallbackRoot = Split-Path $FallbackPython -Parent
            Write-Warning "O instalador oficial pulou o Python (ja existe uma instalacao 3.12 registrada no Windows)."
            Write-Host "Reaproveitando o Python 3.12 encontrado em: $FallbackRoot"
            $SameLocation = (
                [IO.Path]::GetFullPath($FallbackRoot).TrimEnd('\') -eq
                [IO.Path]::GetFullPath($PythonRuntime).TrimEnd('\')
            )
            if (-not $SameLocation) {
                if (Test-Path $PythonRuntime) {
                    Remove-Item -Recurse -Force $PythonRuntime
                }
                New-Item -ItemType Directory -Force -Path $PythonRuntime | Out-Null
                Copy-Item -Recurse -Force -Path (Join-Path $FallbackRoot "*") -Destination $PythonRuntime
            }
        }
    }
    if (-not (Test-Path $PythonExe)) {
        throw "Nao foi possivel preparar o Python 3.12 local. Instale o Python 3.12 (com venv) e execute novamente."
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

Write-Host "Instalando a voz local leve (Piper)..."
Invoke-PipInstall -Arguments @("-r", (Join-Path $ServerDir "requirements-voice.txt"))

if (-not $SkipTtsModel) {
    & $Python (Join-Path $ServerDir "scripts\prepare_tts_voice.py")
    if ($LASTEXITCODE -ne 0) {
        throw "Nao foi possivel preparar as vozes do Piper."
    }
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

$ShortcutInstaller = Join-Path $RootDir "launcher\create_shortcut.ps1"
try {
    & $ShortcutInstaller -InstallRoot $RootDir
} catch {
    Write-Warning "Nao foi possivel criar o atalho: $($_.Exception.Message)"
}

Write-Host "Snake Reyers Lite instalado com voz Piper, Python e Node.js locais."
Write-Host "Use o atalho Snake Reyers Lite na Area de Trabalho para iniciar."
