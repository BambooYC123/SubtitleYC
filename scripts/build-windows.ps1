param(
    [string]$Version = "0.4.0",
    [string]$ReleaseLabel = "0.4.0",
    [switch]$BundleExternalTools,
    [switch]$SkipAppCompile,
    [switch]$SkipPortableZip,
    [ValidateSet("CPU", "GPU-CUDA-12.9")]
    [string]$VideOCRVariant = "CPU",
    [string]$VideOCRCliPath = $env:VIDEOCR_CLI,
    [string]$FFmpegPath = $env:FFMPEG_BINARY,
    [string]$FFprobePath = $env:FFPROBE_BINARY,
    [string]$ArtifactsRoot,
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
if ($BundleExternalTools -and ([bool]$FFmpegPath -xor [bool]$FFprobePath)) {
    throw "Pass both -FFmpegPath and -FFprobePath, or omit both to use PATH."
}
$BuildVenv = Join-Path $Root ".build-venv"
$Python = Join-Path $BuildVenv "Scripts\python.exe"
$PyInstaller = Join-Path $BuildVenv "Scripts\pyinstaller.exe"
$LockFile = Join-Path $Root "requirements-release.txt"
$BuildDir = Join-Path $ArtifactsRoot "build"
$DistDir = Join-Path $ArtifactsRoot "dist\SubtitleYC"
$ReleaseDir = Join-Path $ArtifactsRoot "release"
$EditionSlug = $VideOCRVariant.ToLowerInvariant()
$BundleSuffix = if ($BundleExternalTools) { "-$EditionSlug" } else { "" }
$ZipPath = Join-Path $ReleaseDir "SubtitleYC-$ReleaseLabel-windows$BundleSuffix.zip"

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
    param(
        [string]$Path,
        [string]$CertificateThumbprint,
        [string]$TimeStampServer,
        [string]$RequestedSignTool,
        [switch]$SigningRequired
    )

    if (-not $CertificateThumbprint) {
        if ($SigningRequired) {
            throw "Release signing is required. Set SUBTITLEYC_SIGNING_CERT_THUMBPRINT or pass -SigningCertificateThumbprint."
        }
        Write-Warning "Code signing skipped for $Path. This build is suitable for local testing, not a trusted public release."
        return
    }
    $signTool = Find-SignTool -RequestedPath $RequestedSignTool
    if (-not $signTool) {
        throw "signtool.exe was not found. Install the Windows SDK or pass -SignToolPath."
    }
    $thumbprint = $CertificateThumbprint -replace '\s', ''
    Invoke-Checked { & $signTool sign /sha1 $thumbprint /fd SHA256 /tr $TimeStampServer /td SHA256 $Path }
    Invoke-Checked { & $signTool verify /pa $Path }
}

function Resolve-CommandSource {
    param(
        [string]$Name,
        [string]$RequestedPath
    )
    if ($RequestedPath) {
        if (-not (Test-Path $RequestedPath)) {
            throw "Requested $Name executable does not exist: $RequestedPath"
        }
        return (Resolve-Path $RequestedPath).Path
    }
    $command = Get-Command $Name -ErrorAction SilentlyContinue | Select-Object -First 1
    if (-not $command -or -not $command.Source -or -not (Test-Path $command.Source)) {
        return $null
    }
    return (Resolve-Path $command.Source).Path
}

function Test-VideOCRVariantPath {
    param(
        [string]$Path,
        [string]$Variant
    )

    $normalized = $Path.ToLowerInvariant()
    switch ($Variant) {
        "CPU" { return $normalized -match 'videocr' -and $normalized -match 'cpu' -and $normalized -notmatch 'gpu' }
        "GPU-CUDA-12.9" { return $normalized -match 'videocr' -and $normalized -match 'gpu' -and $normalized -match 'cuda[-_ ]?12\.9' }
    }
    return $false
}

function Resolve-VideOCRCli {
    param(
        [string]$RequestedPath,
        [string]$Variant
    )

    if ($RequestedPath) {
        if (-not (Test-Path $RequestedPath)) {
            throw "Requested VideOCR CLI does not exist: $RequestedPath"
        }
        $resolved = (Resolve-Path $RequestedPath).Path
        if (-not (Test-VideOCRVariantPath -Path $resolved -Variant $Variant)) {
            throw "VideOCR path does not match release variant $Variant`: $resolved"
        }
        return $resolved
    }

    $matches = @()
    foreach ($root in @("C:\Program Files\VideOCR", "C:\Program Files (x86)\VideOCR")) {
        if (Test-Path $root) {
            $matches += Get-ChildItem -LiteralPath $root -Recurse -Filter "videocr-cli.exe" -File -ErrorAction SilentlyContinue |
                Where-Object { Test-VideOCRVariantPath -Path $_.FullName -Variant $Variant }
        }
    }
    $match = $matches | Sort-Object FullName -Descending | Select-Object -First 1
    if ($match) {
        return $match.FullName
    }
    return $null
}

function Copy-LicenseBundle {
    param(
        [string]$TargetDistDir,
        [string]$PythonExecutable
    )

    $requiredFiles = @(
        "LICENSE",
        "PRIVACY.md",
        "SECURITY.md",
        "THIRD-PARTY-NOTICES.txt",
        "licenses\VideOCR-MIT.txt",
        "licenses\yt-dlp-Unlicense.txt",
        "licenses\GPL-3.0.txt",
        "licenses\LGPL-3.0.txt"
    )
    foreach ($relativePath in $requiredFiles) {
        if (-not (Test-Path (Join-Path $Root $relativePath))) {
            throw "Required release license file is missing: $relativePath"
        }
    }

    foreach ($releaseDocument in @("LICENSE", "PRIVACY.md", "SECURITY.md", "THIRD-PARTY-NOTICES.txt")) {
        Copy-Item -LiteralPath (Join-Path $Root $releaseDocument) -Destination $TargetDistDir -Force
    }

    $targetLicenseDir = Join-Path $TargetDistDir "licenses"
    if (Test-Path $targetLicenseDir) {
        Remove-Item -LiteralPath $targetLicenseDir -Recurse -Force
    }
    Copy-Item -LiteralPath (Join-Path $Root "licenses") -Destination $TargetDistDir -Recurse -Force

    $sitePackages = (& $PythonExecutable -c "import site; print(next(p for p in site.getsitepackages() if p.endswith('site-packages')))" ).Trim()
    if ($LASTEXITCODE -ne 0 -or -not (Test-Path $sitePackages)) {
        throw "Could not locate build-environment site-packages for license collection."
    }

    $pythonLicenseDir = Join-Path $targetLicenseDir "python"
    New-Item -ItemType Directory -Force -Path $pythonLicenseDir | Out-Null
    $manifest = [System.Collections.Generic.List[string]]::new()
    $manifest.Add("Python distribution license files included in this build")
    $manifest.Add("Generated: $([DateTime]::UtcNow.ToString('yyyy-MM-ddTHH:mm:ssZ'))")
    $manifest.Add("")

    Get-ChildItem -LiteralPath $sitePackages -Directory -Filter "*.dist-info" | Sort-Object Name | ForEach-Object {
        $distribution = $_
        $licenseFiles = Get-ChildItem -LiteralPath $distribution.FullName -Recurse -File -ErrorAction SilentlyContinue |
            Where-Object {
                $_.FullName -match '(?i)[\\/]licenses?[\\/]' -or
                $_.Name -match '^(?i:LICENSE|COPYING|NOTICE)'
            }
        if (-not $licenseFiles) {
            return
        }

        $distributionTarget = Join-Path $pythonLicenseDir $distribution.Name
        foreach ($licenseFile in $licenseFiles) {
            $relativeLicensePath = $licenseFile.FullName.Substring($distribution.FullName.Length).TrimStart("\")
            $licenseTarget = Join-Path $distributionTarget $relativeLicensePath
            New-Item -ItemType Directory -Force -Path (Split-Path -Parent $licenseTarget) | Out-Null
            Copy-Item -LiteralPath $licenseFile.FullName -Destination $licenseTarget -Force
            $manifest.Add("$($distribution.Name)\$relativeLicensePath")
        }
    }

    Set-Content -LiteralPath (Join-Path $pythonLicenseDir "MANIFEST.txt") -Value $manifest -Encoding UTF8
}
function Copy-BundledTools {
    param(
        [string]$TargetDistDir,
        [string]$RequestedVideOCRCliPath,
        [string]$VideOCRBuildVariant,
        [string]$RequestedFFmpegPath,
        [string]$RequestedFFprobePath
    )

    $toolsDir = Join-Path $TargetDistDir "tools"
    if (Test-Path $toolsDir) {
        Remove-Item -LiteralPath $toolsDir -Recurse -Force
    }
    New-Item -ItemType Directory -Force -Path $toolsDir | Out-Null

    $resolvedVideOCRCli = Resolve-VideOCRCli -RequestedPath $RequestedVideOCRCliPath -Variant $VideOCRBuildVariant
    if (-not $resolvedVideOCRCli) {
        throw "VideOCR $VideOCRBuildVariant CLI was not found. Install that VideOCR edition or pass its executable with -VideOCRCliPath."
    }

    $videOCRSourceDir = Split-Path -Parent $resolvedVideOCRCli
    Write-Host "Bundling VideOCR $VideOCRBuildVariant from $videOCRSourceDir"
    Copy-Item -LiteralPath $videOCRSourceDir -Destination $toolsDir -Recurse -Force
    $buildMetadata = @{
        variant = $VideOCRBuildVariant.ToLowerInvariant()
        gpu_default = $VideOCRBuildVariant.StartsWith("GPU-", [StringComparison]::OrdinalIgnoreCase)
        source_directory = Split-Path -Leaf $videOCRSourceDir
        source_cli_sha256 = (Get-FileHash -LiteralPath $resolvedVideOCRCli -Algorithm SHA256).Hash.ToLowerInvariant()
    } | ConvertTo-Json
    Set-Content -LiteralPath (Join-Path $toolsDir "videocr-build.json") -Value $buildMetadata -Encoding UTF8

    $ffmpegSource = Resolve-CommandSource -Name "ffmpeg" -RequestedPath $RequestedFFmpegPath
    $ffprobeSource = Resolve-CommandSource -Name "ffprobe" -RequestedPath $RequestedFFprobePath
    if (-not $ffmpegSource -or -not $ffprobeSource) {
        throw "ffmpeg and ffprobe are required. Pass -FFmpegPath and -FFprobePath, or make both available on PATH."
    }

    $ffmpegTargetDir = Join-Path $toolsDir "ffmpeg"
    New-Item -ItemType Directory -Force -Path $ffmpegTargetDir | Out-Null
    Write-Host "Bundling ffmpeg from $ffmpegSource"
    Copy-Item -LiteralPath $ffmpegSource -Destination (Join-Path $ffmpegTargetDir "ffmpeg.exe") -Force
    Copy-Item -LiteralPath $ffprobeSource -Destination (Join-Path $ffmpegTargetDir "ffprobe.exe") -Force

    $ffmpegSourceDir = Split-Path -Parent $ffmpegSource
    $ffprobeSourceDir = Split-Path -Parent $ffprobeSource
    @($ffmpegSourceDir, $ffprobeSourceDir) | Sort-Object -Unique | ForEach-Object {
        Get-ChildItem -LiteralPath $_ -Filter "*.dll" -File -ErrorAction SilentlyContinue |
            Copy-Item -Destination $ffmpegTargetDir -Force
    }
    $ffmpegDllCount = @(Get-ChildItem -LiteralPath $ffmpegTargetDir -Filter "*.dll" -File -ErrorAction SilentlyContinue).Count
    $ffmpegHash = (Get-FileHash -LiteralPath $ffmpegSource -Algorithm SHA256).Hash.ToLowerInvariant()
    $ffprobeHash = (Get-FileHash -LiteralPath $ffprobeSource -Algorithm SHA256).Hash.ToLowerInvariant()
    $ffmpegVersionOutput = (& $ffmpegSource -version 2>&1 | Out-String).Trim()
    if ($LASTEXITCODE -ne 0) {
        throw "Bundled ffmpeg could not report its version and build configuration."
    }
    $ffprobeVersionOutput = (& $ffprobeSource -version 2>&1 | Out-String).Trim()
    if ($LASTEXITCODE -ne 0) {
        throw "Bundled ffprobe could not report its version and build configuration."
    }

    @{
        ffmpeg_sha256 = $ffmpegHash
        ffprobe_sha256 = $ffprobeHash
        shared_build = $ffmpegDllCount -gt 0
        dll_count = $ffmpegDllCount
    } | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $toolsDir "ffmpeg-build.json") -Encoding UTF8

    $ffmpegPackageDir = Split-Path -Parent $ffmpegSourceDir
    $ffmpegLicenseDir = Join-Path $TargetDistDir "licenses\FFmpeg-build"
    New-Item -ItemType Directory -Force -Path $ffmpegLicenseDir | Out-Null
    foreach ($fileName in @("LICENSE", "README.txt")) {
        $sourceFile = Join-Path $ffmpegPackageDir $fileName
        if (Test-Path $sourceFile) {
            Copy-Item -LiteralPath $sourceFile -Destination $ffmpegLicenseDir -Force
        }
    }
    $ffmpegBuildInfo = @(
        "SubtitleYC bundled FFmpeg build information",
        "Generated: $([DateTime]::UtcNow.ToString('yyyy-MM-ddTHH:mm:ssZ'))",
        "ffmpeg SHA-256: $ffmpegHash",
        "ffprobe SHA-256: $ffprobeHash",
        "Shared build: $($ffmpegDllCount -gt 0)",
        "Bundled DLL count: $ffmpegDllCount",
        "",
        "ffmpeg -version",
        "---------------",
        $ffmpegVersionOutput,
        "",
        "ffprobe -version",
        "----------------",
        $ffprobeVersionOutput
    )
    Set-Content -LiteralPath (Join-Path $ffmpegLicenseDir "BUILD-INFO.txt") -Value $ffmpegBuildInfo -Encoding UTF8

    $thirdPartyNotice = @"
Bundled third-party tools
=========================

This folder contains VideOCR and FFmpeg binaries copied from the build machine.
See ..\THIRD-PARTY-NOTICES.txt and ..\licenses for copyright notices, license
texts, source links, and build information.
"@
    Set-Content -LiteralPath (Join-Path $toolsDir "README-THIRD-PARTY.txt") -Value $thirdPartyNotice -Encoding UTF8
}

function Optimize-PackagedRuntime {
    param([string]$TargetDistDir)

    $pysideDir = Join-Path $TargetDistDir "_internal\PySide6"
    if (-not (Test-Path $pysideDir)) {
        return
    }

    $removedBytes = 0L
    $localesDir = Join-Path $pysideDir "translations\qtwebengine_locales"
    if (Test-Path $localesDir) {
        Get-ChildItem -LiteralPath $localesDir -File -ErrorAction SilentlyContinue |
            Where-Object { $_.Name -notin @("en-GB.pak", "en-US.pak") } |
            ForEach-Object {
                $removedBytes += $_.Length
                Remove-Item -LiteralPath $_.FullName -Force
            }
    }

    Write-Host "Optimized packaged Qt runtime: removed $([math]::Round($removedBytes / 1MB, 1)) MB of unused WebEngine locale data"
}

Set-Location $Root

if (-not $SkipAppCompile) {
    if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
        throw "Python 3.10+ is required to build SubtitleYC."
    }

    if (-not (Test-Path $Python)) {
        Invoke-Checked { python -m venv $BuildVenv }
    }

    if (-not (Test-Path $LockFile)) {
        throw "The hashed release lock is missing: $LockFile"
    }

    Write-Host "Installing hash-verified release dependencies"
    Invoke-Checked { & $Python -m pip install --require-hashes --only-binary=:all: -r $LockFile }
    Invoke-Checked { & $Python -m pip install --no-build-isolation --no-deps -e "." }
    Invoke-Checked { & $Python -m pip check }
    Write-Host "Auditing locked dependencies"
    Invoke-Checked { & $Python -m pip_audit -r $LockFile --strict }

    if (-not (Test-Path $PyInstaller)) {
        throw "PyInstaller was not installed by the release lock."
    }
    Invoke-Checked { & $PyInstaller --clean --noconfirm --workpath $BuildDir --distpath (Join-Path $ArtifactsRoot "dist") "SubtitleYC.spec" }

    if (-not (Test-Path (Join-Path $DistDir "SubtitleYC.exe"))) {
        throw "Build failed: dist\SubtitleYC\SubtitleYC.exe was not created."
    }
    Invoke-CodeSign `
        -Path (Join-Path $DistDir "SubtitleYC.exe") `
        -CertificateThumbprint $SigningCertificateThumbprint `
        -TimeStampServer $TimestampUrl `
        -RequestedSignTool $SignToolPath `
        -SigningRequired:$RequireSigning
} elseif (-not (Test-Path (Join-Path $DistDir "SubtitleYC.exe"))) {
    throw "-SkipAppCompile requires an existing dist\SubtitleYC\SubtitleYC.exe build."
} else {
    Write-Host "Reusing compiled SubtitleYC app and replacing bundled tools for $VideOCRVariant"
}

Optimize-PackagedRuntime -TargetDistDir $DistDir

$DistWorkspace = Join-Path $DistDir "workspace"
if (Test-Path $DistWorkspace) {
    Remove-Item -LiteralPath $DistWorkspace -Recurse -Force
}
Copy-Item -LiteralPath (Join-Path $Root "README.md") -Destination (Join-Path $DistDir "README.md") -Force
Copy-LicenseBundle -TargetDistDir $DistDir -PythonExecutable $Python

if ($BundleExternalTools) {
    Copy-BundledTools -TargetDistDir $DistDir -RequestedVideOCRCliPath $VideOCRCliPath -VideOCRBuildVariant $VideOCRVariant -RequestedFFmpegPath $FFmpegPath -RequestedFFprobePath $FFprobePath
}

if ($SkipPortableZip) {
    Write-Host "Skipped portable ZIP creation for installer-only build."
    exit 0
}

New-Item -ItemType Directory -Force -Path $ReleaseDir | Out-Null
if (Test-Path $ZipPath) {
    Remove-Item -LiteralPath $ZipPath -Force
}
$compressed = $false
for ($attempt = 1; $attempt -le 5; $attempt++) {
    try {
        Start-Sleep -Seconds $attempt
        Compress-Archive -Path (Join-Path $DistDir "*") -DestinationPath $ZipPath -Force
        $compressed = $true
        break
    } catch {
        if ($attempt -eq 5) {
            throw
        }
        Write-Host "Zip attempt $attempt failed; retrying..."
    }
}
if (-not $compressed) {
    throw "Build completed, but release zip could not be created."
}

$zipHash = (Get-FileHash -LiteralPath $ZipPath -Algorithm SHA256).Hash.ToLowerInvariant()
$zipHashPath = "$ZipPath.sha256"
Set-Content -LiteralPath $zipHashPath -Value "$zipHash  $(Split-Path -Leaf $ZipPath)" -Encoding ASCII

Write-Host "Built $ZipPath"
Write-Host "SHA-256: $zipHashPath"
if ($BundleExternalTools) {
    Write-Host "Bundled $VideOCRVariant release includes tools copied into dist\SubtitleYC\tools."
} else {
    Write-Host "Users can unzip it and run SubtitleYC.exe after installing VideOCR and ffmpeg."
}
