# SubtitleYC v0.6.0

SubtitleYC is a free and open-source Windows app for extracting, reviewing,
and editing frame-timed subtitles from video.

SubtitleYC is distributed under the MIT License. Bundled third-party tools
retain their own licences, which are included with the installation.

## Changes

- Added a small web installer that downloads and verifies the app and CPU OCR, then installs both. CPU OCR is ready when setup finishes; internet is required during installation.
- Added optional Nvidia GPU OCR in **GPU OCR**, with local GPU/driver checks, download progress, pause/resume, and checksum verification.
- Clarified download size, installed disk usage, temporary installation space, and the estimated combined app/OCR size. The UI distinguishes SubtitleYC 0.6.0 from the VideOCR 1.5.1 engine.
- The welcome screen recognizes the installed CPU package and offers optional GPU setup.
- Added a clearer GPU OCR panel with compatibility checks, a compact installed-CPU status, and expandable storage/download details. Enable **GPU Acceleration** after installing GPU OCR to use it.
- Improved video scrubbing by batching rapid slider updates and preserving the final seek position.
- Kept long video titles clear of preview buttons and added a full-title tooltip.
- Fixed native video covering dialogs and added protection for unsaved subtitle edits.

## Install

Download and run `SubtitleYC-0.6.0-windows-setup.exe` with an internet connection.
Setup downloads the app and CPU OCR from this release and verifies their SHA-256 hashes before removing an older installation. CPU OCR runs locally afterward.

`SubtitleYC-0.6.0-windows-app.zip` and the `SubtitleYC-0.6.0-ocr-*.zip` files are payloads used by setup or the app. Users do not need to extract them manually.

The three payload ZIPs are not standalone installers. Use the setup EXE for installation.

User data stays under `%LOCALAPPDATA%\SubtitleYC\workspace`. Downloaded runtimes
stay separately under `%LOCALAPPDATA%\SubtitleYC\runtimes` across updates and uninstall.

## Known Limitations

- This is an early release and may still contain crashes or UI defects.
- OCR accuracy depends on language, image quality, crop, and source frame rate.
- Video websites change independently; yt-dlp workflows can require app updates.
- GPU runtime downloads are large. Download sizes are shown before you start.
- {{SIGNING_STATUS}}

## Verify the Download

GitHub displays a SHA-256 digest beside each installer asset. To calculate the
digest of a downloaded installer in PowerShell:

```powershell
Get-FileHash .\SubtitleYC-0.6.0-windows-setup.exe -Algorithm SHA256
```

Compare the result with the digest shown on the release page before installation.

Please report reproducible problems through the issue forms. Do not attach
private media or unredacted logs.
