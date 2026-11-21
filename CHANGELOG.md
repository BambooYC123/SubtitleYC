# Changelog

## 0.7.1

SubtitleYC 0.7.1 makes optional Nvidia GPU OCR part of the guided installation flow. Setup can check the local GPU and driver, remember the user’s choice, and hand a resumable first-launch download to the app without delaying the core CPU installation.

- Added an **OCR engines** setup page in English and Simplified Chinese. CPU OCR remains required and works on every supported PC; GPU OCR is offered when setup detects a supported Nvidia GTX 16 or RTX 20–50 card with driver 576.57 or newer.
- Supported systems have GPU OCR selected by default, with its download and installed sizes shown before installation. It can be declined and remains available later from **GPU OCR** in the app.
- When GPU OCR is selected during setup, SubtitleYC starts the download automatically on first launch and shows progress in the bottom activity bar without forcing the runtime dialog to stay open.
- Added pause, resume, retry, verification, and installation states to the activity bar. Pausing an automatic download prevents it from restarting on the next launch.
- GPU Acceleration is enabled automatically after the selected GPU runtime finishes installing.
- Improved first-launch onboarding so unsupported systems are not shown an irrelevant GPU prompt, while systems with no OCR engine still receive setup guidance.
- Added Simplified Chinese translations for the new installer choices and runtime-download progress messages.

## 0.7.0

SubtitleYC 0.7.0 brings extraction and editing into one redesigned workspace. The new timeline, clearer OCR controls, and expanded cue editor make it easier to move from a video to reviewed subtitles, while this release also strengthens cancellation, preview accuracy, and protection against lost work.

- Redesigned the interface around **Extract** and **Edit** modes with a shared light or dark appearance. The extraction workspace now has a collapsible settings column, editable **Fast**, **Balanced**, and **Accurate** OCR profiles, and a separate advanced-settings panel.
- Added a timeline below the video. Subtitle cues appear as blocks; extraction ranges can be set with draggable **IN** and **OUT** markers, and cue edges can be dragged in the editor to adjust timing.
- Expanded the subtitle editor with a roomier cue grid, `mm:ss.mmm` time fields, frame-step controls, duration and reading-speed details, find and replace, and warnings for fast, overlapping, or empty cues.
- Improved the video stage with aspect-ratio-aware framing, a sharper preview on scaled displays, accurate frame decoding near the end of a video, and a crop box with corner handles and a size readout.
- Added clearer job progress and contextual **Edit**, **Upload**, **Save**, and **Export** actions. Errors stay concise and link directly to filtered logs, while Logs and Settings now open as centred dialogs.
- Added confirmation before detaching a video or subtitle file from the preview, plus stronger guards against replacing or losing unsaved subtitle edits.
- Stopping a job or closing the app now terminates OCR, download, and child processes completely. Failed or cancelled OCR runs preserve the subtitles already attached to the project.
- Fixed GPU-only OCR installations failing when **GPU Acceleration** was switched off. A GPU build now always runs with GPU processing enabled.
- Added WebVTT (`.vtt`) subtitle import and fixed `.ass` and `.txt` exports so editor style markup is translated or removed correctly.
- Improved pasted-link handling by extracting URLs from phone share text and recognising supported `rednote.com` note links.
- Fixed the Simplified Chinese setup page displaying as question marks and updated Pillow, yt-dlp, and other bundled libraries.

## 0.6.0

- Web installer, optional GPU OCR downloads, clearer storage information, smoother scrubbing. See the v0.6.0 release notes on GitHub.
