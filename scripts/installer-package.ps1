# Read and validate a fast-start ZIP without extracting its payload to disk.
function Get-InstallerPackageSignature {
    param([string]$Path)
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    $archive = [IO.Compression.ZipFile]::OpenRead($Path)
    $temporaryExe = Join-Path ([IO.Path]::GetTempPath()) ("subtitleyc-signature-" + [guid]::NewGuid().ToString('N') + '.exe')
    try {
        $entries = @($archive.Entries)
        if (@($entries | Where-Object { $_.FullName -ne $_.Name }).Count -gt 0 -or
            @($entries.Name | Select-Object -Unique).Count -ne $entries.Count) {
            throw 'Installer package contains nested or duplicate entries.'
        }
        $executables = @($entries | Where-Object { $_.Name -like '*-setup.exe' })
        $payloads = @($entries | Where-Object { $_.Name -like '*.bin' })
        if ($executables.Count -ne 1 -or $payloads.Count -eq 0 -or -not $archive.GetEntry('START-HERE.txt')) {
            throw 'Installer package is missing its executable, payload, or instructions.'
        }
        foreach ($entry in @($executables) + @($payloads)) {
            $checksum = $archive.GetEntry($entry.Name + '.sha256')
            if (-not $checksum) { throw "Missing checksum for $($entry.Name)" }
            $reader = New-Object IO.StreamReader($checksum.Open())
            try { $expected = ($reader.ReadToEnd().Trim() -split '\s+')[0] } finally { $reader.Dispose() }
            $stream = $entry.Open()
            $hasher = [Security.Cryptography.SHA256]::Create()
            try { $actual = ([BitConverter]::ToString($hasher.ComputeHash($stream))).Replace('-', '') }
            finally { $stream.Dispose(); $hasher.Dispose() }
            if ($expected -ne $actual) { throw "Package checksum mismatch: $($entry.Name)" }
        }
        [IO.Compression.ZipFileExtensions]::ExtractToFile($executables[0], $temporaryExe)
        return Get-AuthenticodeSignature -LiteralPath $temporaryExe
    } finally {
        $archive.Dispose()
        if (Test-Path -LiteralPath $temporaryExe) { Remove-Item -LiteralPath $temporaryExe -Force }
    }
}
