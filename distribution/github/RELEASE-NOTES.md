# SubtitleYC v0.5.2

SubtitleYC is a free and open-source Windows app for extracting, reviewing,
and editing frame-timed subtitles from video.

SubtitleYC is distributed under the MIT License. Bundled third-party tools
retain their own licences, which are included with the installation.

## Changes

- Updated all active maintainer, licence, package, and installer branding to BambooYC123.
- Added controls to remove the current video or subtitles from the active preview without deleting their files from Previous Projects.
- Added a privacy-safe Copy System Info button for troubleshooting and bug reports.
- Changed the load/open-video keyboard shortcut from `Ctrl+O` to `Ctrl+L`.

## Choose an Installer

- CPU is the safest default and does not require an Nvidia GPU.
- CUDA 12.9 is for supported Nvidia GTX 16 through RTX 50 systems.

Installing another edition replaces the app and OCR runtime while preserving
the user's workspace under `%LOCALAPPDATA%\SubtitleYC\workspace`.

## Known Limitations

- This is an early release and may still contain crashes or UI defects.
- OCR accuracy depends on language, image quality, crop, and source frame rate.
- Video websites change independently; yt-dlp workflows can require app updates.
- The GPU installer is large because it includes the CUDA OCR runtime.
- {{SIGNING_STATUS}}

## Verify the Download

GitHub displays a SHA-256 digest beside each installer asset. To calculate the
digest of a downloaded installer in PowerShell:

```powershell
Get-FileHash .\SubtitleYC-0.5.2-windows-cpu-setup.exe -Algorithm SHA256
```

Compare the result with the digest shown on the release page before installation.

Please report reproducible problems through the issue forms. Do not attach
private media or unredacted logs.
