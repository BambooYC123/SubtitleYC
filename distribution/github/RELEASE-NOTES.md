# SubtitleYC v0.7.1

SubtitleYC is a free and open-source Windows app for extracting, reviewing,
and editing frame-timed subtitles from burned-in video captions.

SubtitleYC is distributed under the MIT License. Bundled third-party tools
retain their own licences, which are included with the installation.

Version 0.7.1 makes optional Nvidia GPU OCR part of the guided installation
flow. Setup can check the local GPU and driver, remember the user's choice, and
hand a resumable first-launch download to the app without delaying the core CPU
installation.

## Changes

- Added an **OCR engines** setup page in English and Simplified Chinese. CPU OCR remains required; GPU OCR is offered when setup detects a supported Nvidia GTX 16 or RTX 20–50 card with driver 576.57 or newer.
- Supported systems have GPU OCR selected by default, with its download and installed sizes shown before installation. It can be declined and remains available later from **GPU OCR** in the app.
- When GPU OCR is selected during setup, SubtitleYC starts the download automatically on first launch and shows progress in the bottom activity bar without forcing the runtime dialog to stay open.
- Added pause, resume, retry, verification, and installation states to the activity bar. Pausing an automatic download prevents it from restarting on the next launch.
- GPU Acceleration is enabled automatically after the selected GPU runtime finishes installing.
- Improved first-launch onboarding so unsupported systems are not shown an irrelevant GPU prompt, while systems with no OCR engine still receive setup guidance.
- Added Simplified Chinese translations for the new installer choices and runtime-download progress messages.

## Install

Download and run `SubtitleYC-0.7.1-windows-setup.exe` with an internet connection.
Setup downloads the app and CPU OCR from this release and verifies their SHA-256 hashes before removing an older installation. CPU OCR runs locally afterward.

`SubtitleYC-0.7.1-windows-app.zip` and the `SubtitleYC-0.7.1-ocr-*.zip` files are payloads used by setup or the app. Users do not need to extract them manually.

The three payload ZIPs are not standalone installers. Use the setup EXE for installation.

User data stays under `%LOCALAPPDATA%\SubtitleYC\workspace`. Downloaded runtimes
stay separately under `%LOCALAPPDATA%\SubtitleYC\runtimes` across updates and uninstall.

## Known Limitations

- This is an early release and may still contain crashes or UI defects.
- OCR accuracy depends on language, image quality, crop, and source frame rate.
- Video websites change independently; yt-dlp workflows can require app updates.
- GPU runtime downloads are large. Download sizes are shown before you start.
- The Fast and Accurate profiles are starting points and have not been tuned against a benchmark.
- {{SIGNING_STATUS}}

## Verify the Download

GitHub displays a SHA-256 digest beside each installer asset. To calculate the
digest of a downloaded installer in PowerShell:

```powershell
Get-FileHash .\SubtitleYC-0.7.1-windows-setup.exe -Algorithm SHA256
```

Compare the result with the digest shown on the release page before installation.

Please report reproducible problems through the issue forms. Do not attach
private media or unredacted logs.
