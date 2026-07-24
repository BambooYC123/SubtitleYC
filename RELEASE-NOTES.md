# SubtitleYC v0.2.0 Beta 1

This is the first public testing release of SubtitleYC for 64-bit Windows.

## Highlights

- Local video and URL workflows in one desktop app.
- Native PyAV frame preview with crop selection and subtitle overlay.
- CPU and Nvidia GPU VideOCR editions.
- Subtitle import, cue timing edits, undo/redo, and SRT export.
- yt-dlp format and site-subtitle discovery.
- Project library, storage controls, activity rows, local logs, and crash logs.
- Dark and light themes with persisted settings.

## Choose an Installer

- CPU is the safest default and does not require an Nvidia GPU.
- CUDA 12.9 is for supported Nvidia GTX 16 through RTX 50 systems.
- CUDA 11.8 is optional and appears only when a legacy build is published.

Installing another edition replaces the app and OCR runtime while preserving
the user's workspace under `%LOCALAPPDATA%\SubtitleYC\workspace`.

## Known Limitations

- This is prerelease software and may still contain crashes or UI defects.
- OCR accuracy depends on language, image quality, crop, and source frame rate.
- Video websites change independently; yt-dlp workflows can require app updates.
- The GPU installer is large because it includes the CUDA OCR runtime.
- These beta installers are not Authenticode-signed. Windows may show an unknown-publisher warning; verify the SHA-256 checksum before running them.

## Verify the Download

Every installer is accompanied by a `.sha256` file. In PowerShell:

```powershell
Get-FileHash .\SubtitleYC-0.2.0-beta.1-windows-cpu-setup.exe -Algorithm SHA256
```

Compare the result with the corresponding checksum file before installation.

Please report reproducible problems through the issue forms. Do not attach
private media or unredacted logs.

