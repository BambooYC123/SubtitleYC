# SubtitleYC v0.2.0 Beta 2

SubtitleYC is a free and open-source Windows app for extracting, reviewing,
and editing frame-timed subtitles from video.

## MIT Release

Beta 2 is the first release whose installers, bundled application files, and
installer licence page consistently use the MIT License. Bundled third-party
tools retain their own licences, which are included with the installation.

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

Installing another edition replaces the app and OCR runtime while preserving
the user's workspace under `%LOCALAPPDATA%\SubtitleYC\workspace`.

## Known Limitations

- This is prerelease software and may still contain crashes or UI defects.
- OCR accuracy depends on language, image quality, crop, and source frame rate.
- Video websites change independently; yt-dlp workflows can require app updates.
- The GPU installer is large because it includes the CUDA OCR runtime.
- {{SIGNING_STATUS}}

## Verify the Download

GitHub displays a SHA-256 digest beside each installer asset. To calculate the
digest of a downloaded installer in PowerShell:

```powershell
Get-FileHash .\SubtitleYC-0.2.0-beta.2-windows-cpu-setup.exe -Algorithm SHA256
```

Compare the result with the digest shown on the release page before installation.

Please report reproducible problems through the issue forms. Do not attach
private media or unredacted logs.
