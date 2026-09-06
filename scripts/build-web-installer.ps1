param(
    [string]$Version = '0.6.0',
    [string]$ArtifactsRoot,
    [string]$InnoSetupCompiler = "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe",
    [string]$Python = "$env:SUBTITLEYC_BUILD_VENV\Scripts\python.exe",
    [switch]$SkipPayloadBuild,
    [string]$SigningCertificateThumbprint = $env:SUBTITLEYC_SIGNING_CERT_THUMBPRINT,
    [string]$SignToolPath,
    [string]$TimestampUrl = 'http://timestamp.digicert.com',
    [switch]$RequireSigning
)
$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
$ArtifactsRoot = (Resolve-Path -LiteralPath $ArtifactsRoot).Path
$release = Join-Path $ArtifactsRoot 'release'
if (-not $SkipPayloadBuild) {
    & $Python (Join-Path $PSScriptRoot 'package-web-installer.py') --dist (Join-Path $ArtifactsRoot 'dist\SubtitleYC') --output $release --version $Version --catalog (Join-Path $Root 'assets\runtime-catalog.json')
    if ($LASTEXITCODE -ne 0) { throw 'Web payload packaging failed' }
}
& $InnoSetupCompiler "/DWebInstaller=1" "/DWebPayloadInclude=$(Join-Path $release 'web-payload.iss')" "/DAppVersion=$Version" "/DAppDisplayVersion=$Version" '/DAppEdition=CPU OCR included; optional GPU download' "/DOutputDir=$release" "/DOutputBaseFilename=SubtitleYC-$Version-windows-setup" (Join-Path $Root 'installer\SubtitleYC.iss')
if ($LASTEXITCODE -ne 0) { throw 'Web installer compilation failed' }
$setup = Join-Path $release "SubtitleYC-$Version-windows-setup.exe"
if ($SigningCertificateThumbprint) {
    if (-not $SignToolPath) { $SignToolPath = (Get-Command signtool.exe -ErrorAction Stop).Source }
    & $SignToolPath sign /sha1 $SigningCertificateThumbprint /fd SHA256 /tr $TimestampUrl /td SHA256 $setup
    if ($LASTEXITCODE -ne 0) { throw 'Web installer signing failed' }
    & $SignToolPath verify /pa $setup
    if ($LASTEXITCODE -ne 0) { throw 'Web installer signature verification failed' }
} elseif ($RequireSigning) { throw 'Web installer release signing was required but no certificate was supplied' }
$hash = (Get-FileHash -LiteralPath $setup -Algorithm SHA256).Hash.ToLowerInvariant()
Set-Content -LiteralPath "$setup.sha256" -Encoding ASCII -Value "$hash  $(Split-Path -Leaf $setup)"
Write-Host "Web installer created: $setup"
