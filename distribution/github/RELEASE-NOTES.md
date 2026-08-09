# SubtitleYC v0.5.0

SubtitleYC is a free and open-source Windows app for extracting, reviewing,
and editing frame-timed subtitles from video.

SubtitleYC is distributed under the MIT License. Bundled third-party tools
retain their own licences, which are included with the installation.

## Highlights

- Local video and URL workflows in one desktop app.
- Native PyAV frame preview with crop selection and subtitle overlay.
- CPU and Nvidia GPU VideOCR editions.
- 31 alphabetically listed OCR language choices, including common Asian languages.
- Correct Simplified and Traditional Chinese VideOCR language mapping.
- Subtitle import, cue timing edits, undo/redo, and SRT export.
- Bold, italic, underline, and colour styling for selected subtitle text or whole cues.
- Safe styled-subtitle rendering in both browser and native desktop previews.
- Editor shortcut tooltips for formatting, playback, navigation, save, reload, undo/redo, and deletion.
- yt-dlp format and site-subtitle discovery.
- Project library, storage controls, activity rows, local logs, and crash logs.
- Dark and light themes with persisted settings.
- English and Simplified Chinese app interfaces.
- Static self-identifying language choices (`English` and `中文`) in the app and installer.
- A complete Simplified Chinese README linked from the main project README.
- English or Simplified Chinese can be selected on the installer's first screen.
- The installer language becomes the app language on first launch and can be changed later in Settings.

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
Get-FileHash .\SubtitleYC-0.5.0-windows-cpu-setup.exe -Algorithm SHA256
```

Compare the result with the digest shown on the release page before installation.

Please report reproducible problems through the issue forms. Do not attach
private media or unredacted logs.
