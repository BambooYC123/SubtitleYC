# SubtitleYC Public Beta Release Checklist

## Project and Licensing

- [ ] Publish the complete corresponding SubtitleYC source for the release tag.
- [ ] Include `LICENSE`, `CONTRIBUTING.md`, `PRIVACY.md`, and `SECURITY.md`.
- [ ] Confirm every third-party version and licence against the final binaries.
- [ ] Archive or link the corresponding source and build information for the exact GPL FFmpeg build.
- [ ] Confirm the Privacy Notice still matches actual network and storage behaviour.
- [ ] Publish one stable private security contact or enable Private Vulnerability Reporting.

## Build and Verification

- [ ] Build CPU and CUDA 12.9 installers in one `build-public-releases.ps1` run.
- [ ] Run the complete automated test suite and dependency audit.
- [ ] Test install, launch, OCR, download, edit, export, upgrade, and uninstall on a clean Windows VM.
- [ ] Test CPU mode on a PC without an Nvidia GPU.
- [ ] Test GPU mode on at least one supported Nvidia system.
- [ ] Verify every SHA-256 file against its installer.
- [ ] Authenticode-sign and timestamp production installers, or prominently disclose an unsigned beta.
- [ ] Scan the final public files after signing and before upload.

## GitHub Release

- [ ] Publish the source repository under the MIT License.
- [ ] Enable GitHub Issues, Discussions, and Private Vulnerability Reporting.
- [ ] Publish `v0.2.0-beta.1` as a prerelease from the exact tested commit.
- [ ] Upload the CPU installer, CUDA 12.9 installer, and every matching `.sha256` file.
- [ ] Make CPU the recommended default and explain the GPU hardware requirement.
- [ ] Keep each GitHub release asset below 2 GiB.
- [ ] Do not commit installers, signing keys, certificates, logs, user media, build output, or workspace data.

## Beta Operation

- [ ] Recruit a small first group before promoting broadly.
- [ ] Ask for Windows version, edition, video source, and reproducible steps in bug reports.
- [ ] Review issues and pull requests at a predictable cadence.
- [ ] Update yt-dlp promptly when supported sites change; test VideOCR and FFmpeg updates before bundling them.
- [ ] Publish fixes as new installers; users install over the existing app and keep their workspace.
- [ ] Keep the last known-good release available if a new beta regresses.

This checklist is operational guidance, not legal advice.