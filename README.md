# SubtitleYC

SubtitleYC is a local Windows app for extracting, reviewing, and editing
frame-timed subtitles from burned-in video captions. It combines a native PyAV
preview, VideOCR, yt-dlp, and FFmpeg in one desktop workflow.

> **Public beta:** This release is intended for testing and may contain defects.
> Keep backups and review generated subtitles before relying on them.

## Download

Download the latest beta from [GitHub Releases](https://github.com/EricYC123/SubtitleYC/releases/tag/v0.2.0-beta.1).
Do not download SubtitleYC from third-party mirrors.

- **CPU installer:** Recommended for most users and works without an Nvidia GPU.
- **GPU CUDA 12.9 installer:** Faster OCR for supported Nvidia GTX 16 through RTX 50 systems, but substantially larger.

CUDA 11.8 is not included in this beta. Nvidia GTX 10 users should install the
CPU edition.

These beta installers are not Authenticode-signed. Windows may show an unknown-publisher warning; verify the SHA-256 checksum before running them.

Each installer has a matching `.sha256` file. Verify the checksum before
running an unsigned beta installer.

## What It Does

- Opens local videos or downloads user-authorised video URLs with yt-dlp.
- Provides smooth native frame scrubbing and a draggable subtitle crop region.
- Runs CPU or Nvidia GPU VideOCR for burned-in captions.
- Imports, edits, previews, and exports frame-timed subtitles.
- Stores projects, settings, logs, and generated files locally.

## Requirements

- 64-bit Windows 10 or Windows 11.
- Several gigabytes of free disk space for installation and working video files.
- A compatible Nvidia GPU and driver only for the GPU edition.

## Feedback and Support

Use [GitHub Issues](https://github.com/EricYC123/SubtitleYC/issues) for reproducible bugs and feature
requests. Use [GitHub Discussions](https://github.com/EricYC123/SubtitleYC/discussions) for general
feedback. Do not post private videos, credentials, cookies, access tokens, or
unredacted logs.

Security reports must follow [SECURITY.md](SECURITY.md), not a public issue.

## Privacy and Licensing

SubtitleYC processes media locally and has no telemetry in this beta. Network
features contact websites selected by the user. Read the [Privacy Notice](PRIVACY.md).

SubtitleYC's original application code is proprietary. Downloading or viewing
this releases repository does not grant access to that private source code.
Use of the app is governed by the [EULA](EULA.txt) and [Beta Terms](BETA-TERMS.txt).
Bundled components remain under their own licences; see
[Third-Party Notices](THIRD-PARTY-NOTICES.txt).

Publisher: **EricYC123**  
Support: https://github.com/EricYC123/SubtitleYC/issues

