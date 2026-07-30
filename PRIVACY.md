# SubtitleYC Privacy Notice

Effective date: 22 July 2026

This notice describes the SubtitleYC Windows desktop application. It does not
replace the privacy terms of websites or services that a user chooses to
access through the app.

## Short Version

SubtitleYC 0.3.0 does not include accounts, advertising, analytics,
telemetry, a licence server, or automatic crash-report uploads. Videos,
subtitles, settings, and logs are processed and stored on the user's computer.
Nothing is sent to the SubtitleYC maintainers unless the user chooses to submit
it in a support or feedback report.

## Data Stored Locally

SubtitleYC may store the following on the user's computer:

- selected or copied videos and subtitle files;
- downloaded videos and website subtitle files;
- generated subtitles, preview data, and OCR working files;
- app settings, file paths, job status, and local logs; and
- local crash reports when the app encounters an unhandled error.

Packaged Windows builds use `%LOCALAPPDATA%\SubtitleYC\workspace` by default.
Users may select other download folders or set `SUBTITLEYC_DATA_DIR`. The
Storage and Logs screens can review or remove supported data categories.
Uninstalling the application may leave the workspace in place so user-created
files are not silently deleted.

## Network Activity

SubtitleYC runs a private backend on the loopback address `127.0.0.1` for its
desktop interface. This service is intended to be reachable only from the same
computer and is protected by an app-session token.

When a user enters a video URL or asks to download website subtitles,
SubtitleYC and yt-dlp contact that website and related media hosts. Those
services can receive normal connection information such as the user's IP
address, requested URL, and user-agent details. Their own terms and privacy
policies apply. SubtitleYC does not operate those services.

SubtitleYC does not automatically check for app updates. Windows, antivirus,
certificate, or operating-system services may independently perform their own
reputation or security checks.

## Logs and Support Reports

Logs remain local unless the user deliberately shares them. SubtitleYC removes
or masks common secrets, URL query values, and sensitive local-network details
where practical, but automated redaction cannot be guaranteed to catch every
case. Users should review logs before submitting them and should not attach
private videos, credentials, cookies, or access tokens.

## User Choices

Users can choose where downloads are stored, whether selected local videos are
copied into the SubtitleYC workspace, and which generated files to remove.
Users can stop using the app and delete its workspace at any time, subject to
normal Windows file permissions and any files they intentionally saved
elsewhere.

## Changes and Contact

Material changes to this notice will be identified in a future release. The
official repository identifies the maintainers and current privacy/support
contact channel.
