# OCR runtime distribution (0.7.0)

The recommended download is `SubtitleYC-0.7.0-windows-setup.exe`, a small web installer. It downloads two pinned ZIPs: the app with FFmpeg/ffprobe, and CPU VideOCR. Both hashes are checked before an existing app is uninstalled. Inno Setup extracts and registers all files in one setup flow. CPU OCR is ready at first launch; GPU remains an optional in-app download.

The initial EXE contains setup code and archive support rather than the large payload. Windows checks can still affect startup speed. Internet is required during setup. Failed/cancelled downloads leave the existing app intact; users can retry. Downloads are held in the setup temporary folder and cleaned up when setup exits.

CPU OCR is installed under the app's `tools/VideOCR` folder and removed with the app. Optional managed runtime downloads live separately under `%LOCALAPPDATA%/SubtitleYC/runtimes` and survive updates/uninstall.

## Building and publishing

`scripts/build-public-releases.ps1` packages the two VideOCR runtime directories
using `scripts/package-runtimes.py`, then builds the core app and uses `scripts/build-web-installer.ps1` to package its ZIP and compile the web installer. The generated
`assets/runtime-catalog.json` is included in the app and records exact GitHub
release URLs, sizes, CLI paths and SHA-256 checksums. CPU/GPU must use the same
VideOCR version. Keep the generated catalog with the corresponding source.

Publish the web EXE, **app payload ZIP and both runtime ZIPs** to the catalog's release tag
(initially `v0.7.0`). Do not replace runtime assets after publishing: publish a
new app/catalog for changed binaries. Runtime hashes also serve as installation
identities, so an app update using the same catalog hashes reuses the files.
`-OfflineInstallers` additionally builds the full CPU/GPU setup ZIPs.

Keep SHA-256 sidecars and `PUBLIC-BUILD-MANIFEST.json` as build records. Staging
checks the hashes of every asset and signatures of setup executables. Runtime
ZIPs are pinned by checksum, not Authenticode-signed as archives.

## Storage and interruption

Optional downloaded runtimes live under `%LOCALAPPDATA%\SubtitleYC\runtimes`, outside the app folder
and workspace cache. `SUBTITLEYC_RUNTIME_DIR` overrides this for development.
They are retained on upgrade/uninstall. Workspace storage cleanup cannot delete
them. Users can remove this directory while SubtitleYC is closed to reclaim it.

Only one process may install a runtime at a time. Downloads use HTTPS, a finite
network timeout, exact size bounds, and HTTP Range resume where supported. A
server that ignores Range restarts the download. Pause or application exit keeps
the partial archive; the user explicitly resumes it. Checksum failure discards
the archive so a retry starts cleanly.

Extraction happens only after SHA-256 verification, into a staging directory.
Traversal, Windows device paths, alternate streams, duplicate names and symbolic
links are rejected. The unpacked size must match the catalog. An atomic directory
rename and completion marker activate the runtime only after extraction succeeds.
Free space is checked for the remaining download, extracted runtime and headroom.

## Release validation

Run the Python suite and JavaScript checks. On clean Windows systems, verify core
install and launch, editor use without OCR, CPU and GPU downloads, pause/resume,
offline errors and retry, successful OCR, app upgrade with runtime reuse, and
uninstall retention. Test the published version-specific asset URLs before
promoting the release; local fixture tests cannot establish GitHub availability
or GPU driver compatibility.

## First-launch setup

CUDA downloads require a local preflight: `nvidia-smi` must report a documented GeForce GTX 16 or RTX 20–50 model and driver 576.57 or newer (the conservative full CUDA 12.9 Update 1 requirement). Other models and failed probes are described as unverified, not necessarily incompatible. The disabled GPU choice provides an explanation and a recheck button; CPU remains available. Results are cached for 30 seconds, with a fresh check before every GPU download. This preflight does not guarantee sufficient VRAM or a successful OCR run.

Setup installs CPU OCR automatically. The first-launch GPU OCR panel shows CPU as ready and offers an optional Nvidia GPU download. The CPU download card appears only if CPU OCR is missing. After GPU installation, enable GPU Acceleration in OCR settings. Opening the panel never starts a download. Dismissal is stored in the workspace's `.ocr-setup-seen` marker, independently of UI settings, and survives app updates. GPU OCR remains available afterward.

Native video is hidden while a modal dialog is visible in either workspace, including runtime downloads and confirmation dialogs, and restored when the modal closes. Every native preview update includes the visibility decision so playback cannot raise the video over a modal.

## Size reporting

The build measures the core app payload and includes `install-size.json`. The UI estimates app-plus-OCR disk usage from this measurement and the catalog's unpacked sizes; projects, caches, extra models and filesystem allocation overhead are excluded. For a missing runtime, required additional free space equals remaining compressed bytes plus unpacked bytes plus 256 MiB of headroom. An installed runtime requires no additional download space. CPU and GPU coexist; GPU does not replace CPU.

SubtitleYC is version 0.7.0. VideOCR remains engine version 1.5.1; public package filenames use the SubtitleYC release version: `SubtitleYC-0.7.0-ocr-cpu.zip` and `SubtitleYC-0.7.0-ocr-gpu-cuda-12.9.zip`. The engine version remains in the catalog and expandable technical details for traceability. Size units are MiB/GiB.
