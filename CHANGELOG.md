# Changelog

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
