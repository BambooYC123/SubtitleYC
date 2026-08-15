param(
    [string]$AppVersion = "0.5.2",
    [string]$ReleaseTag = "v0.5.2",
    [Parameter(Mandatory = $true)]
    [string]$ArtifactsRoot,
    [Parameter(Mandatory = $true)]
    [string]$Destination,
    [string]$MaintainerName = "BambooYC123",
    [Parameter(Mandatory = $true)]
    [string]$SupportUrl,
    [Parameter(Mandatory = $true)]
    [string]$RepositoryUrl,
    [switch]$AllowUnsigned
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$TemplateDir = Join-Path $Root "distribution\github"

function Assert-HttpsUrl {
    param([string]$Name, [string]$Value)

    $uri = $null
    if (-not [Uri]::TryCreate($Value, [UriKind]::Absolute, [ref]$uri) -or $uri.Scheme -ne 'https') {
        throw "$Name must be an absolute HTTPS URL."
    }
}

if ([string]::IsNullOrWhiteSpace($MaintainerName) -or $MaintainerName -match '(?i)replace|placeholder|todo') {
    throw "Provide the public maintainer name."
}
Assert-HttpsUrl -Name "SupportUrl" -Value $SupportUrl
Assert-HttpsUrl -Name "RepositoryUrl" -Value $RepositoryUrl
if ($ReleaseTag -notmatch '^v\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?$') {
    throw "ReleaseTag must look like v0.5.2 or v0.5.2-beta.1."
}
$releaseLabel = $ReleaseTag.Substring(1)

$resolvedArtifactsRoot = (Resolve-Path -LiteralPath $ArtifactsRoot).Path
$manifestFiles = @(Get-ChildItem -LiteralPath $resolvedArtifactsRoot -Recurse -Filter "PUBLIC-BUILD-MANIFEST.json" -File)
if ($manifestFiles.Count -ne 1) {
    throw "Expected exactly one PUBLIC-BUILD-MANIFEST.json under ArtifactsRoot; found $($manifestFiles.Count)."
}
$manifestPath = $manifestFiles[0].FullName
$manifest = Get-Content -LiteralPath $manifestPath -Raw | ConvertFrom-Json
if ([string]$manifest.app_version -ne $AppVersion) {
    throw "Build manifest version '$($manifest.app_version)' does not match requested version '$AppVersion'."
}
if ([string]$manifest.release_label -ne $releaseLabel) {
    throw "Build manifest release '$($manifest.release_label)' does not match requested release '$releaseLabel'."
}

$requiredEditions = @(
    "SubtitleYC-$releaseLabel-windows-cpu-setup.exe",
    "SubtitleYC-$releaseLabel-windows-gpu-cuda-12.9-setup.exe"
)
$manifestNames = @($manifest.artifacts | ForEach-Object { [string]$_.file_name })
foreach ($requiredEdition in $requiredEditions) {
    if ($requiredEdition -notin $manifestNames) {
        throw "The single-run public build manifest is missing $requiredEdition."
    }
}

if ($manifestNames.Count -ne $requiredEditions.Count) {
    throw "The public build manifest must contain exactly the CPU and CUDA 12.9 installers."
}

$destinationPath = [IO.Path]::GetFullPath($Destination)
if (Test-Path -LiteralPath $destinationPath) {
    if (@(Get-ChildItem -LiteralPath $destinationPath -Force).Count -gt 0) {
        throw "Destination must be empty: $destinationPath"
    }
} else {
    New-Item -ItemType Directory -Path $destinationPath -Force | Out-Null
}
$repositoryDir = Join-Path $destinationPath "repository"
$releaseAssetsDir = Join-Path $destinationPath "release-assets"
New-Item -ItemType Directory -Path $repositoryDir, $releaseAssetsDir -Force | Out-Null
$sourceInputs = @(
    "subtitleyc", "static", "scripts", "installer", "tests", "assets", "docs", "distribution", "licenses",
    ".gitignore", "CONTRIBUTING.md", "LICENSE", "PRIVACY.md",
    "pyproject.toml", "README.md", "README.CN.md", "requirements-release.txt", "SECURITY.md", "Start-SubtitleYC.bat",
    "SubtitleYC.spec", "THIRD-PARTY-NOTICES.txt"
)
foreach ($sourceInput in $sourceInputs) {
    $sourcePath = Join-Path $Root $sourceInput
    if (-not (Test-Path -LiteralPath $sourcePath)) {
        throw "Open-source staging input is missing: $sourceInput"
    }
    Copy-Item -LiteralPath $sourcePath -Destination $repositoryDir -Recurse -Force
}
Copy-Item -LiteralPath (Join-Path $TemplateDir ".github") -Destination $repositoryDir -Recurse -Force

$allSigned = $true

foreach ($artifact in @($manifest.artifacts)) {
    $fileName = [string]$artifact.file_name
    $sourcePath = Join-Path (Split-Path -Parent $manifestPath) $fileName
    $sourceChecksumPath = "$sourcePath.sha256"
    if (-not (Test-Path -LiteralPath $sourcePath -PathType Leaf) -or
        -not (Test-Path -LiteralPath $sourceChecksumPath -PathType Leaf)) {
        throw "Manifest artifact or checksum is missing: $fileName"
    }
    $file = Get-Item -LiteralPath $sourcePath
    if ($file.Length -ge 2GB) {
        throw "$fileName is $($file.Length) bytes and cannot be uploaded as one GitHub release asset."
    }
    $actualHash = (Get-FileHash -LiteralPath $sourcePath -Algorithm SHA256).Hash.ToLowerInvariant()
    $checksumHash = ((Get-Content -LiteralPath $sourceChecksumPath -Raw).Trim() -split '\s+')[0].ToLowerInvariant()
    if ($actualHash -ne ([string]$artifact.sha256).ToLowerInvariant() -or $actualHash -ne $checksumHash) {
        throw "SHA-256 verification failed for $fileName."
    }
    $signature = Get-AuthenticodeSignature -LiteralPath $sourcePath
    if ($signature.Status -ne [System.Management.Automation.SignatureStatus]::Valid) {
        $allSigned = $false
        if (-not $AllowUnsigned) {
            throw "$fileName is not Authenticode-signed. Pass -AllowUnsigned only when the release clearly discloses this."
        }
    }
    Copy-Item -LiteralPath $sourcePath -Destination $releaseAssetsDir -Force
}

$signingStatus = if ($allSigned) {
    "The installers are Authenticode-signed and timestamped."
} else {
    "These installers are not Authenticode-signed. Windows may show an unknown-publisher warning; compare the SHA-256 digest shown by GitHub before running them."
}
$cleanRepositoryUrl = $RepositoryUrl -replace '/+$', ''
$replacements = [ordered]@{
    '{{REPOSITORY_URL}}' = $cleanRepositoryUrl
    '{{RELEASE_TAG}}' = $ReleaseTag
    '{{MAINTAINER_NAME}}' = $MaintainerName
    '{{SUPPORT_URL}}' = $SupportUrl
    '{{SIGNING_STATUS}}' = $signingStatus
}
$textExtensions = @(".bat", ".css", ".html", ".iss", ".js", ".json", ".md", ".ps1", ".py", ".spec", ".toml", ".txt", ".yaml", ".yml")
$templateFiles = @(Get-ChildItem -LiteralPath $repositoryDir -Recurse -File | Where-Object {
    $_.Name -eq ".gitignore" -or $_.Extension.ToLowerInvariant() -in $textExtensions
})
$utf8NoBom = New-Object System.Text.UTF8Encoding($false)
$templateFiles | ForEach-Object {
    $content = [IO.File]::ReadAllText($_.FullName)
    foreach ($replacement in $replacements.GetEnumerator()) {
        $content = $content.Replace($replacement.Key, $replacement.Value)
    }
    [IO.File]::WriteAllText($_.FullName, $content, $utf8NoBom)
}
$unresolvedTemplates = @($templateFiles | Select-String -Pattern '\{\{[A-Z_]+\}\}')
if ($unresolvedTemplates.Count -gt 0) {
    throw "Public repository staging left unresolved template values."
}

$releaseNotes = [IO.File]::ReadAllText((Join-Path $TemplateDir "RELEASE-NOTES.md"))
foreach ($replacement in $replacements.GetEnumerator()) {
    $releaseNotes = $releaseNotes.Replace($replacement.Key, $replacement.Value)
}
[IO.File]::WriteAllText((Join-Path $destinationPath "RELEASE-NOTES.md"), $releaseNotes, $utf8NoBom)

$screenshotSourceDir = Join-Path $Root "docs\screenshots"
$screenshotTargetDir = Join-Path $repositoryDir "docs\screenshots"
$requiredScreenshots = @(
    "01-project-library.png",
    "02-ocr-workflow.png",
    "03-subtitle-editor.png"
)
New-Item -ItemType Directory -Path $screenshotTargetDir -Force | Out-Null
foreach ($screenshot in $requiredScreenshots) {
    $sourcePath = Join-Path $screenshotSourceDir $screenshot
    if (-not (Test-Path -LiteralPath $sourcePath -PathType Leaf)) {
        throw "Public repository screenshot is missing: $sourcePath"
    }
    Copy-Item -LiteralPath $sourcePath -Destination $screenshotTargetDir -Force
}
Copy-Item -LiteralPath (Join-Path $Root "distribution\RELEASE-CHECKLIST.md") -Destination $destinationPath -Force
Copy-Item -LiteralPath (Join-Path $Root "distribution\BETA-PROGRAM.md") -Destination $destinationPath -Force

Write-Host "Staged public repository: $repositoryDir" -ForegroundColor Green
Write-Host "Staged GitHub release assets: $releaseAssetsDir" -ForegroundColor Green
Write-Host "Release tag: $ReleaseTag"
Write-Host "Signing: $signingStatus"
