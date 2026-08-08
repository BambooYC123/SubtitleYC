param(
    [string]$Version = "0.4.0",
    [string]$ReleaseLabel = "0.4.0",
    [switch]$BundleExternalTools,
    [switch]$SkipAppBuild,
    [switch]$SkipPortableZip,
    [ValidateSet("CPU", "GPU-CUDA-12.9")]
    [string]$VideOCRVariant = "CPU",
    [string]$VideOCRCliPath = $env:VIDEOCR_CLI,
    [string]$FFmpegPath = $env:FFMPEG_BINARY,
    [string]$FFprobePath = $env:FFPROBE_BINARY,
    [string]$ArtifactsRoot,
    [string]$InnoSetupCompiler,
    [string]$SigningCertificateThumbprint = $env:SUBTITLEYC_SIGNING_CERT_THUMBPRINT,
    [string]$TimestampUrl = "http://timestamp.digicert.com",
    [string]$SignToolPath,
    [switch]$RequireSigning
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
if (-not $ArtifactsRoot) {
    $ArtifactsRoot = $Root
}
New-Item -ItemType Directory -Force -Path $ArtifactsRoot | Out-Null
$ArtifactsRoot = (Resolve-Path $ArtifactsRoot).Path
$DistDir = Join-Path $ArtifactsRoot "dist\SubtitleYC"
$ReleaseDir = Join-Path $ArtifactsRoot "release"
$InstallerScript = Join-Path $Root "installer\SubtitleYC.iss"

function Invoke-Checked {
    param([scriptblock]$Command)
    & $Command
    if ($LASTEXITCODE -ne 0) {
        throw "Command failed with exit code $LASTEXITCODE"
    }
}

function Find-SignTool {
    param([string]$RequestedPath)

    $candidates = @()
    if ($RequestedPath) {
        $candidates += $RequestedPath
    }
    $pathCommand = Get-Command "signtool.exe" -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($pathCommand -and $pathCommand.Source) {
        $candidates += $pathCommand.Source
    }
    $sdkRoot = Join-Path ${env:ProgramFiles(x86)} "Windows Kits\10\bin"
    if (Test-Path $sdkRoot) {
        $candidates += Get-ChildItem -LiteralPath $sdkRoot -Recurse -Filter "signtool.exe" -File -ErrorAction SilentlyContinue |
            Where-Object { $_.FullName -match '[\\/]x64[\\/]signtool\.exe$' } |
            Sort-Object FullName -Descending |
            ForEach-Object { $_.FullName }
    }
    foreach ($candidate in $candidates) {
        if ($candidate -and (Test-Path $candidate)) {
            return (Resolve-Path $candidate).Path
        }
    }
    return $null
}

function Invoke-CodeSign {
    param([string]$Path)

    if (-not $SigningCertificateThumbprint) {
        if ($RequireSigning) {
            throw "Release signing is required. Set SUBTITLEYC_SIGNING_CERT_THUMBPRINT or pass -SigningCertificateThumbprint."
        }
        Write-Warning "Code signing skipped for $Path. This build is suitable for local testing, not a trusted public release."
        return
    }
    $signTool = Find-SignTool -RequestedPath $SignToolPath
    if (-not $signTool) {
        throw "signtool.exe was not found. Install the Windows SDK or pass -SignToolPath."
    }
    $thumbprint = $SigningCertificateThumbprint -replace '\s', ''
    Invoke-Checked { & $signTool sign /sha1 $thumbprint /fd SHA256 /tr $TimestampUrl /td SHA256 $Path }
    Invoke-Checked { & $signTool verify /pa $Path }
}

function Find-InnoSetupCompiler {
    param([string]$RequestedPath)

    $candidates = @()
    if ($RequestedPath) {
        $candidates += $RequestedPath
    }

    $pathCommand = Get-Command "iscc.exe" -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($pathCommand -and $pathCommand.Source) {
        $candidates += $pathCommand.Source
    }

    $candidates += @(
        (Join-Path $env:LOCALAPPDATA "Programs\Inno Setup 6\ISCC.exe"),
        (Join-Path $env:LOCALAPPDATA "Programs\Inno Setup 5\ISCC.exe"),
        "C:\Program Files (x86)\Inno Setup 6\ISCC.exe",
        "C:\Program Files\Inno Setup 6\ISCC.exe",
        "C:\Program Files (x86)\Inno Setup 5\ISCC.exe",
        "C:\Program Files\Inno Setup 5\ISCC.exe"
    )

    foreach ($candidate in $candidates) {
        if ($candidate -and (Test-Path $candidate)) {
            return (Resolve-Path $candidate).Path
        }
    }

    return $null
}

Set-Location $Root

if (-not $SkipAppBuild) {
    $buildArgs = @(
        "-Version", $Version,
        "-ReleaseLabel", $ReleaseLabel,
        "-TimestampUrl", $TimestampUrl,
        "-ArtifactsRoot", $ArtifactsRoot
    )
    if ($SigningCertificateThumbprint) {
        $buildArgs += @("-SigningCertificateThumbprint", $SigningCertificateThumbprint)
    }
    if ($SignToolPath) {
        $buildArgs += @("-SignToolPath", $SignToolPath)
    }
    if ($RequireSigning) {
        $buildArgs += "-RequireSigning"
    }
    if ($SkipPortableZip) {
        $buildArgs += "-SkipPortableZip"
    }
    if ($BundleExternalTools) {
        $buildArgs += @("-BundleExternalTools", "-VideOCRVariant", $VideOCRVariant)
        if ($VideOCRCliPath) {
            $buildArgs += @("-VideOCRCliPath", $VideOCRCliPath)
        }
        if ($FFmpegPath) {
            $buildArgs += @("-FFmpegPath", $FFmpegPath)
        }
        if ($FFprobePath) {
            $buildArgs += @("-FFprobePath", $FFprobePath)
        }
    }
    $buildScript = Join-Path $Root "scripts\build-windows.ps1"
    & powershell -ExecutionPolicy Bypass -File $buildScript @buildArgs
    if ($LASTEXITCODE -ne 0) {
        throw "App build failed with exit code $LASTEXITCODE"
    }
}

if (-not (Test-Path (Join-Path $DistDir "SubtitleYC.exe"))) {
    throw "dist\SubtitleYC\SubtitleYC.exe was not found. Run scripts\build-windows.ps1 first, or omit -SkipAppBuild."
}

foreach ($releaseDocument in @("README.md", "LICENSE", "PRIVACY.md", "SECURITY.md", "THIRD-PARTY-NOTICES.txt")) {
    $releaseDocumentPath = Join-Path $Root $releaseDocument
    if (-not (Test-Path -LiteralPath $releaseDocumentPath -PathType Leaf)) {
        throw "Required release document was not found: $releaseDocument"
    }
    Copy-Item -LiteralPath $releaseDocumentPath -Destination (Join-Path $DistDir $releaseDocument) -Force
}
if ($SkipAppBuild) {
    Invoke-CodeSign -Path (Join-Path $DistDir "SubtitleYC.exe")
}

if ($BundleExternalTools) {
    $toolsDir = Join-Path $DistDir "tools"
    $bundledVideOCR = $null
    if (Test-Path $toolsDir) {
        $bundledVideOCR = Get-ChildItem -LiteralPath $toolsDir -Recurse -Filter "videocr-cli.exe" -File -ErrorAction SilentlyContinue | Select-Object -First 1
    }
    $buildMetadataPath = Join-Path $toolsDir "videocr-build.json"
    if (-not $bundledVideOCR -or -not (Test-Path (Join-Path $toolsDir "ffmpeg\ffmpeg.exe")) -or -not (Test-Path (Join-Path $toolsDir "ffmpeg\ffprobe.exe")) -or -not (Test-Path $buildMetadataPath)) {
        throw "Bundled tools and edition metadata were not found in dist\SubtitleYC\tools. Run without -SkipAppBuild, or rebuild the requested edition first."
    }
    $buildMetadata = Get-Content -LiteralPath $buildMetadataPath -Raw | ConvertFrom-Json
    if ([string]$buildMetadata.variant -ne $VideOCRVariant.ToLowerInvariant()) {
        throw "Existing dist edition '$($buildMetadata.variant)' does not match requested installer edition '$($VideOCRVariant.ToLowerInvariant())'."
    }
}

$iscc = Find-InnoSetupCompiler -RequestedPath $InnoSetupCompiler
if (-not $iscc) {
    throw "Inno Setup compiler was not found. Install Inno Setup 6, then rerun this script. Download/package id: JRSoftware.InnoSetup."
}

New-Item -ItemType Directory -Force -Path $ReleaseDir | Out-Null
$sourceDir = (Resolve-Path $DistDir).Path
$outputDir = (Resolve-Path $ReleaseDir).Path
$editionSlug = $VideOCRVariant.ToLowerInvariant()
$suffix = if ($BundleExternalTools) { "-$editionSlug" } else { "" }
$editionName = if (-not $BundleExternalTools) {
    "External Tools Edition"
} else {
    switch ($VideOCRVariant) {
        "CPU" { "CPU Edition" }
        "GPU-CUDA-12.9" { "GPU Edition (CUDA 12.9)" }
    }
}
$outputBaseFilename = "SubtitleYC-$ReleaseLabel-windows$suffix-setup"
$compilerArguments = @(
    "/DAppVersion=$Version",
    "/DAppDisplayVersion=$ReleaseLabel",
    "/DAppEdition=$editionName",
    "/DSourceDir=$sourceDir",
    "/DOutputDir=$outputDir",
    "/DOutputBaseFilename=$outputBaseFilename"
)

Invoke-Checked {
    & $iscc @compilerArguments $InstallerScript
}

$installerPath = Join-Path $ReleaseDir "$outputBaseFilename.exe"
if (-not (Test-Path $installerPath)) {
    throw "Installer build finished but $installerPath was not created."
}
Invoke-CodeSign -Path $installerPath

$installerHash = (Get-FileHash -LiteralPath $installerPath -Algorithm SHA256).Hash.ToLowerInvariant()
$installerHashPath = "$installerPath.sha256"
Set-Content -LiteralPath $installerHashPath -Value "$installerHash  $(Split-Path -Leaf $installerPath)" -Encoding ASCII

Write-Host "Built $installerPath"
Write-Host "SHA-256: $installerHashPath"
Write-Host "Built SubtitleYC $editionName. Installing another edition replaces its bundled OCR runtime."
