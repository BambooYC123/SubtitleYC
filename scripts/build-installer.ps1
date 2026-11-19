param(
    [string]$Version = "0.7.0",
    [string]$ReleaseLabel = "0.7.0",
    [switch]$BundleExternalTools,
    [switch]$CoreInstaller,
    [switch]$SkipAppBuild,
    [switch]$SkipPortableZip,
    [switch]$SplitPayload,
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
if ($CoreInstaller -and $BundleExternalTools) {
    throw "Choose either -CoreInstaller or -BundleExternalTools, not both."
}
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
    $previousPreference = $ErrorActionPreference
    try {
        $ErrorActionPreference = "Continue"
        & $Command
        $commandExitCode = $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $previousPreference
    }
    if ($commandExitCode -ne 0) {
        throw "Command failed with exit code $commandExitCode"
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
    if ($CoreInstaller) { $buildArgs += "-CoreInstaller" }
    if ($BundleExternalTools -or $CoreInstaller) {
        if (-not $CoreInstaller) {
            $buildArgs += @("-BundleExternalTools", "-VideOCRVariant", $VideOCRVariant)
        }
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
    Invoke-Checked { & powershell -ExecutionPolicy Bypass -File $buildScript @buildArgs }
}

if (-not (Test-Path (Join-Path $DistDir "SubtitleYC.exe"))) {
    throw "dist\SubtitleYC\SubtitleYC.exe was not found. Run scripts\build-windows.ps1 first, or omit -SkipAppBuild."
}

foreach ($releaseDocument in @("README.md", "README.CN.md", "LICENSE", "PRIVACY.md", "SECURITY.md", "THIRD-PARTY-NOTICES.txt")) {
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
if ($CoreInstaller) {
    foreach ($required in @("tools\ffmpeg\ffmpeg.exe", "tools\ffmpeg\ffprobe.exe", "_internal\assets\runtime-catalog.json")) {
        if (-not (Test-Path -LiteralPath (Join-Path $sourceDir $required))) {
            throw "Core installer is missing $required. Package runtimes and rebuild first."
        }
    }
    if (Get-ChildItem (Join-Path $sourceDir "tools") -Recurse -Filter "videocr-cli.exe" -File) {
        throw "The core installer must not bundle an OCR runtime. Rebuild with -CoreInstaller."
    }
}
$editionSlug = $VideOCRVariant.ToLowerInvariant()
$suffix = if ($BundleExternalTools) { "-$editionSlug" } else { "" }
$editionName = if ($CoreInstaller) {
    "Download OCR runtimes in app"
} elseif (-not $BundleExternalTools) {
    "External Tools Edition"
} else {
    switch ($VideOCRVariant) {
        "CPU" { "CPU Edition" }
        "GPU-CUDA-12.9" { "GPU Edition (CUDA 12.9)" }
    }
}
$outputBaseFilename = "SubtitleYC-$ReleaseLabel-windows$suffix-setup"
if ($SplitPayload) {
    # Isolate companion files from the single-executable public release pipeline.
    $splitOutputDir = Join-Path $outputDir "$outputBaseFilename-fast-start-$([guid]::NewGuid().ToString('N'))"
    New-Item -ItemType Directory -Path $splitOutputDir | Out-Null
    $outputDir = $splitOutputDir
}
$compilerArguments = @(
    "/DAppVersion=$Version",
    "/DAppDisplayVersion=$ReleaseLabel",
    "/DAppEdition=$editionName",
    "/DSourceDir=$sourceDir",
    "/DOutputDir=$outputDir",
    "/DOutputBaseFilename=$outputBaseFilename"
)
if ($SplitPayload) {
    $compilerArguments += "/DSplitPayload=1"
}

Invoke-Checked {
    & $iscc @compilerArguments $InstallerScript
}

$installerPath = Join-Path $outputDir "$outputBaseFilename.exe"
if (-not (Test-Path $installerPath)) {
    throw "Installer build finished but $installerPath was not created."
}
Invoke-CodeSign -Path $installerPath

$installerHash = (Get-FileHash -LiteralPath $installerPath -Algorithm SHA256).Hash.ToLowerInvariant()
$installerHashPath = "$installerPath.sha256"
Set-Content -LiteralPath $installerHashPath -Value "$installerHash  $(Split-Path -Leaf $installerPath)" -Encoding ASCII

if ($SplitPayload) {
    $payloadFiles = @(Get-ChildItem -LiteralPath $outputDir -Filter "$outputBaseFilename-*.bin" -File)
    if ($payloadFiles.Count -eq 0) {
        throw "Fast-start installer build did not create its required payload files."
    }
    foreach ($payloadFile in $payloadFiles) {
        $payloadHash = (Get-FileHash -LiteralPath $payloadFile.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
        Set-Content -LiteralPath "$($payloadFile.FullName).sha256" -Value "$payloadHash  $($payloadFile.Name)" -Encoding ASCII
    }
    Set-Content -LiteralPath (Join-Path $outputDir "START-HERE.txt") -Encoding UTF8 -Value @"
SubtitleYC fast-start installer

Keep the setup EXE and ALL .bin files together in this folder.
Run $outputBaseFilename.exe to install SubtitleYC.
If this folder came in a ZIP, extract the entire ZIP before running Setup.
The small EXE allows Windows to finish its startup checks sooner; the setup
window then provides installation progress while unpacking the payload.
Windows security checks may still delay the first window on some computers.
"@
    Write-Host "Fast-start package: $outputDir"
    Write-Host "Distribute the entire folder, including all .bin files and START-HERE.txt."
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    $packagePath = Join-Path $ReleaseDir "$outputBaseFilename.zip"
    # BIN files are already compressed. Store them without an expensive second pass.
    [IO.Compression.ZipFile]::CreateFromDirectory($outputDir, $packagePath, [IO.Compression.CompressionLevel]::NoCompression, $false)
    if ((Get-Item -LiteralPath $packagePath).Length -ge 2GB) {
        throw "Package exceeds GitHub's per-asset limit: $packagePath. Distribute its individual EXE and BIN files instead."
    }
    $packageHash = (Get-FileHash -LiteralPath $packagePath -Algorithm SHA256).Hash.ToLowerInvariant()
    Set-Content -LiteralPath "$packagePath.sha256" -Value "$packageHash  $(Split-Path -Leaf $packagePath)" -Encoding ASCII
    Write-Host "GitHub release package: $packagePath"
}

Write-Host "Built $installerPath"
Write-Host "SHA-256: $installerHashPath"
Write-Host "Built SubtitleYC $editionName. Installing another edition replaces its bundled OCR runtime."
