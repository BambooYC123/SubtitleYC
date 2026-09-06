param(
    [string]$Version = "0.6.0",
    [string]$ReleaseLabel = "0.6.0",
    [switch]$OfflineInstallers,
    [Parameter(Mandatory = $true)]
    [string]$CpuVideOCRCliPath,
    [Parameter(Mandatory = $true)]
    [string]$GpuCuda129VideOCRCliPath,
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
$WindowsBuildScript = Join-Path $Root "scripts\build-windows.ps1"
$InstallerBuildScript = Join-Path $Root "scripts\build-installer.ps1"
. (Join-Path $Root "scripts\installer-package.ps1")

function Invoke-BuildScript {
    param(
        [string]$Script,
        [string[]]$Arguments
    )

    $previousPreference = $ErrorActionPreference
    try {
        # Windows PowerShell can treat harmless native stderr as terminating errors.
        $ErrorActionPreference = "Continue"
        & powershell -ExecutionPolicy Bypass -File $Script @Arguments
        $buildExitCode = $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $previousPreference
    }
    if ($buildExitCode -ne 0) {
        throw "Release build failed with exit code $buildExitCode`: $Script $($Arguments -join ' ')"
    }
}

function Common-SigningArguments {
    $arguments = @("-TimestampUrl", $TimestampUrl)
    if ($SigningCertificateThumbprint) {
        $arguments += @("-SigningCertificateThumbprint", $SigningCertificateThumbprint)
    }
    if ($SignToolPath) {
        $arguments += @("-SignToolPath", $SignToolPath)
    }
    if ($RequireSigning) {
        $arguments += "-RequireSigning"
    }
    return $arguments
}

function Get-VideOCRVersionFromPath {
    param([string]$Path)

    $match = [regex]::Match($Path, '(?i)v(\d+\.\d+\.\d+)')
    if (-not $match.Success) {
        throw "VideOCR path must include a version such as v1.5.1 for public release traceability: $Path"
    }
    return $match.Groups[1].Value
}

function Build-Edition {
    param(
        [string]$Variant,
        [string]$VideOCRCliPath,
        [switch]$CompileApp
    )

    if (-not (Test-Path $VideOCRCliPath)) {
        throw "VideOCR CLI for $Variant was not found: $VideOCRCliPath"
    }
    Write-Host ""
    Write-Host "Building public $Variant edition" -ForegroundColor Cyan

    $toolArguments = @()
    if ($FFmpegPath) {
        $toolArguments += @("-FFmpegPath", $FFmpegPath, "-FFprobePath", $FFprobePath)
    }
    $signingArguments = Common-SigningArguments
    if ($CompileApp) {
        $installerArguments = @(
            "-Version", $Version,
            "-ReleaseLabel", $ReleaseLabel,
            "-BundleExternalTools",
            "-SplitPayload",
            "-SkipPortableZip",
            "-VideOCRVariant", $Variant,
            "-VideOCRCliPath", $VideOCRCliPath,
            "-ArtifactsRoot", $ArtifactsRoot
        ) + $toolArguments + $signingArguments
        if ($InnoSetupCompiler) {
            $installerArguments += @("-InnoSetupCompiler", $InnoSetupCompiler)
        }
        Invoke-BuildScript -Script $InstallerBuildScript -Arguments $installerArguments
        return
    }

    $appBuildArguments = @(
        "-Version", $Version,
        "-ReleaseLabel", $ReleaseLabel,
        "-BundleExternalTools",
        "-SkipAppCompile",
        "-SkipPortableZip",
        "-VideOCRVariant", $Variant,
        "-VideOCRCliPath", $VideOCRCliPath,
        "-ArtifactsRoot", $ArtifactsRoot
    ) + $toolArguments + $signingArguments
    Invoke-BuildScript -Script $WindowsBuildScript -Arguments $appBuildArguments

    $installerArguments = @(
        "-Version", $Version,
        "-ReleaseLabel", $ReleaseLabel,
        "-BundleExternalTools",
        "-SplitPayload",
        "-SkipAppBuild",
        "-VideOCRVariant", $Variant,
        "-ArtifactsRoot", $ArtifactsRoot
    ) + $signingArguments
    if ($InnoSetupCompiler) {
        $installerArguments += @("-InnoSetupCompiler", $InnoSetupCompiler)
    }
    Invoke-BuildScript -Script $InstallerBuildScript -Arguments $installerArguments
}

Set-Location $Root
if ([bool]$FFmpegPath -xor [bool]$FFprobePath) {
    throw "Pass both -FFmpegPath and -FFprobePath, or omit both to use PATH."
}
foreach ($toolPath in @($FFmpegPath, $FFprobePath)) {
    if ($toolPath -and -not (Test-Path -LiteralPath $toolPath -PathType Leaf)) {
        throw "FFmpeg executable was not found: $toolPath"
    }
}
$videOCRVersion = Get-VideOCRVersionFromPath -Path $CpuVideOCRCliPath
$gpuCuda129Version = Get-VideOCRVersionFromPath -Path $GpuCuda129VideOCRCliPath
if ($gpuCuda129Version -ne $videOCRVersion) {
    throw "CPU VideOCR v$videOCRVersion and CUDA 12.9 VideOCR v$gpuCuda129Version do not match. Stage one VideOCR version for every public edition."
}
Write-Host "Building SubtitleYC with VideOCR v$videOCRVersion across all editions" -ForegroundColor Cyan

$releaseDir = Join-Path $ArtifactsRoot "release"
$packagePython = if ($env:SUBTITLEYC_BUILD_VENV) { Join-Path $env:SUBTITLEYC_BUILD_VENV "Scripts\python.exe" } else { "python" }
& $packagePython (Join-Path $Root "scripts\package-runtimes.py") --cpu (Split-Path -Parent $CpuVideOCRCliPath) --gpu (Split-Path -Parent $GpuCuda129VideOCRCliPath) --output $releaseDir --release $ReleaseLabel
if ($LASTEXITCODE -ne 0) { throw "OCR runtime packaging failed." }
$coreArguments = @("-Version", $Version, "-ReleaseLabel", $ReleaseLabel, "-CoreInstaller", "-SkipPortableZip", "-ArtifactsRoot", $ArtifactsRoot) + (Common-SigningArguments)
if ($FFmpegPath) { $coreArguments += @("-FFmpegPath", $FFmpegPath, "-FFprobePath", $FFprobePath) }
Invoke-BuildScript -Script $WindowsBuildScript -Arguments $coreArguments
$webArguments = @('-Version', $Version, '-ArtifactsRoot', $ArtifactsRoot, '-Python', $packagePython) + (Common-SigningArguments)
if ($InnoSetupCompiler) { $webArguments += @('-InnoSetupCompiler', $InnoSetupCompiler) }
Invoke-BuildScript -Script (Join-Path $Root 'scripts/build-web-installer.ps1') -Arguments $webArguments
if ($OfflineInstallers) {
    Build-Edition -Variant "CPU" -VideOCRCliPath $CpuVideOCRCliPath
    Build-Edition -Variant "GPU-CUDA-12.9" -VideOCRCliPath $GpuCuda129VideOCRCliPath
}

$sourceFiles = @()
foreach ($sourceInput in @(
    "subtitleyc", "static", "scripts", "installer", "tests", "assets", "distribution",
    "pyproject.toml", "requirements-release.txt", "SubtitleYC.spec", "README.md", "README.CN.md",
    "LICENSE", "CONTRIBUTING.md", "PRIVACY.md", "SECURITY.md", "THIRD-PARTY-NOTICES.txt",
    ".gitignore", "Start-SubtitleYC.bat"
)) {
    $sourcePath = Join-Path $Root $sourceInput
    if (Test-Path -LiteralPath $sourcePath -PathType Container) {
        $sourceFiles += Get-ChildItem -LiteralPath $sourcePath -Recurse -File -ErrorAction Stop
    } elseif (Test-Path -LiteralPath $sourcePath -PathType Leaf) {
        $sourceFiles += Get-Item -LiteralPath $sourcePath
    }
}
$sourceFiles = $sourceFiles |
    Where-Object { $_.FullName -notmatch '[\\/]__pycache__[\\/]' -and $_.Extension -notin @('.pyc', '.pyo') } |
    Sort-Object FullName -Unique
$sourceRows = foreach ($sourceFile in $sourceFiles) {
    $relativePath = $sourceFile.FullName.Substring($Root.Length).TrimStart('\')
    $hash = (Get-FileHash -LiteralPath $sourceFile.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
    "$hash  $relativePath"
}
$sourceBytes = [Text.Encoding]::UTF8.GetBytes(($sourceRows -join "`n"))
$sourceHasher = [Security.Cryptography.SHA256]::Create()
try {
    $sourceFingerprint = ([BitConverter]::ToString($sourceHasher.ComputeHash($sourceBytes))).Replace('-', '').ToLowerInvariant()
} finally {
    $sourceHasher.Dispose()
}

$releaseDir = Join-Path $ArtifactsRoot "release"
$expectedInstallers = @(
    "SubtitleYC-$ReleaseLabel-windows-setup.exe",
    "SubtitleYC-$ReleaseLabel-windows-app.zip",
    "SubtitleYC-$ReleaseLabel-ocr-cpu.zip",
    "SubtitleYC-$ReleaseLabel-ocr-gpu-cuda-12.9.zip"
)
if ($OfflineInstallers) { $expectedInstallers += @(
    "SubtitleYC-$ReleaseLabel-windows-cpu-setup.zip",
    "SubtitleYC-$ReleaseLabel-windows-gpu-cuda-12.9-setup.zip"
) }
$artifactRecords = foreach ($installerName in $expectedInstallers) {
    $installerPath = Join-Path $releaseDir $installerName
    $checksumPath = "$installerPath.sha256"
    if (-not (Test-Path -LiteralPath $installerPath -PathType Leaf) -or
        -not (Test-Path -LiteralPath $checksumPath -PathType Leaf)) {
        throw "Public build artifact is missing: $installerName"
    }
    $signature = if ($installerName -like '*-setup.exe') { Get-AuthenticodeSignature -LiteralPath $installerPath }
        elseif ($installerName -like '*-setup.zip') { Get-InstallerPackageSignature -Path $installerPath }
        else { @{ Status = 'NotApplicable' } }
    [ordered]@{
        file_name = $installerName
        size_bytes = (Get-Item -LiteralPath $installerPath).Length
        sha256 = (Get-FileHash -LiteralPath $installerPath -Algorithm SHA256).Hash.ToLowerInvariant()
        signature_status = [string]$signature.Status
    }
}
$publicBuildManifest = [ordered]@{
    schema_version = 1
    build_id = [guid]::NewGuid().ToString()
    generated_utc = [DateTime]::UtcNow.ToString('yyyy-MM-ddTHH:mm:ssZ')
    app_version = $Version
    release_label = $ReleaseLabel
    videocr_version = $videOCRVersion
    source_fingerprint_sha256 = $sourceFingerprint
    artifacts = @($artifactRecords)
}
$manifestPath = Join-Path $releaseDir "PUBLIC-BUILD-MANIFEST.json"
$publicBuildManifest | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $manifestPath -Encoding UTF8

Write-Host ""
Write-Host "Public release matrix complete." -ForegroundColor Green
Write-Host "Build manifest: $manifestPath"
Write-Host "Publish the web setup EXE, app payload ZIP, and BOTH pinned runtime ZIP assets to v$ReleaseLabel. Runtime downloads require these exact URLs."
Write-Host "Optional offline setup ZIPs can be published as alternatives. Retain checksums and the build manifest."
