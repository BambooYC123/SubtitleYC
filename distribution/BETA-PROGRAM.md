# SubtitleYC Open-Source Beta Program

## Recommended First Release

Publish `v0.2.0-beta.2` free of charge to a small group of Windows users. Treat
it as a real release, but label it clearly as prerelease software. Publish the
tested source commit under the MIT License alongside the installer artifacts.

Start with roughly 20 to 50 testers who use different video sources, languages,
Nvidia generations, and CPU-only PCs. Do not add telemetry just to measure the
beta. Use opt-in issues, discussions, and feedback instead.

## What to Learn

- Whether a new user can choose the correct installer without help.
- Whether install, first launch, and Windows reputation warnings are clear.
- Which sites and formats fail in yt-dlp workflows.
- OCR accuracy and timing across languages, frame rates, and crop positions.
- Memory use and preview responsiveness on ordinary PCs.
- Whether users can find projects, output files, logs, and storage controls.
- Whether contributors can reproduce the development setup and tests.

## Exit Criteria for a Release Candidate

- No known crash or data-loss bug in the normal download, OCR, edit, and export paths.
- Clean-VM installation and upgrade tests pass for CPU and GPU editions.
- Dependency licences and corresponding-source links match final binaries.
- Production installers are Authenticode-signed and timestamped.
- Support, privacy, contribution, and update expectations are published.
- The most common beta usability problems have been resolved or documented.

After beta, publish a signed release candidate from a tagged source commit.
Commercial support, sponsored development, and paid distribution may still be
offered without changing the project's MIT licence.