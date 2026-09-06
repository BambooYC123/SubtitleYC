# SubtitleYC Release Checklist

## Project and Licensing

- [ ] Publish the complete corresponding SubtitleYC source for the release tag.
- [ ] Include `LICENSE`, `CONTRIBUTING.md`, `PRIVACY.md`, and `SECURITY.md`.
- [ ] Confirm every third-party version and licence against the final binaries.
- [ ] Archive or link the corresponding source and build information for the exact GPL FFmpeg build.
- [ ] Confirm the Privacy Notice still matches actual network and storage behaviour.
- [ ] Publish one stable private security contact or enable Private Vulnerability Reporting.

## Build and Verification

- [ ] Build the web EXE, app ZIP and both pinned runtime ZIPs in one `build-public-releases.ps1` run.
- [ ] Test first-use runtime download, interruption/resume, checksum failure, and app upgrade with runtime reuse.
- [ ] Run the complete automated test suite and dependency audit.
- [ ] Test install, launch, OCR, download, edit, export, upgrade, and uninstall on a clean Windows VM.
- [ ] Test CPU mode on a PC without an Nvidia GPU.
- [ ] Test GPU mode on at least one supported Nvidia system.
- [ ] Verify each local SHA-256 record and compare it with the digest GitHub reports after upload.
- [ ] Authenticode-sign and timestamp production installers, or prominently disclose that the installers are unsigned.
- [ ] Scan the final public files after signing and before upload.

## GitHub Release

- [ ] Publish the source repository under the MIT License.
- [ ] Enable GitHub Issues, Discussions, and Private Vulnerability Reporting.
- [ ] Publish `v0.6.0` from the exact tested commit.
- [ ] Upload the web EXE, app ZIP and both runtime ZIPs to the exact release tag in the embedded catalog; retain checksums and the build manifest.
- [ ] Confirm the app payload and both runtime URLs work before promoting the release. Offer optional offline installer ZIPs if built.
- [ ] Include CPU OCR during setup and explain the optional GPU hardware requirement and GPU Acceleration setting.
- [ ] Keep each GitHub release asset below 2 GiB.
- [ ] Do not commit installers, signing keys, certificates, logs, user media, build output, or workspace data.

## Release Operation

- [ ] Recruit a small first group before promoting broadly.
- [ ] Ask for Windows version, edition, video source, and reproducible steps in bug reports.
- [ ] Review issues and pull requests at a predictable cadence.
- [ ] Update yt-dlp promptly when supported sites change; test VideOCR and FFmpeg updates before bundling them.
- [ ] Publish fixes as new installers; users install over the existing app and keep their workspace.
- [ ] Keep the last known-good release available if a new version regresses.

This checklist is operational guidance, not legal advice.
