# SubtitleYC v0.5.1

SubtitleYC is a free and open-source Windows app for extracting, reviewing,
and editing frame-timed subtitles from video.

SubtitleYC is distributed under the MIT License. Bundled third-party tools
retain their own licences, which are included with the installation.

## Changes

- Smoother Subtitle Editor timeline scrubbing. Native preview requests are now coalesced so stale frame decodes cannot queue behind the latest slider position.
- A larger Subtitle Editor video preview. The 16:9 preview now uses more horizontal room and expands into the previously unused space below it.

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
Get-FileHash .\SubtitleYC-0.5.1-windows-cpu-setup.exe -Algorithm SHA256
```

Compare the result with the digest shown on the release page before installation.

Please report reproducible problems through the issue forms. Do not attach
private media or unredacted logs.
