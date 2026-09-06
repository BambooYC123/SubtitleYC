# Installer startup

Before 0.6.0, the normal release was one EXE containing the application and OCR runtime.
Windows may check the entire executable before the installer can show any UI.
A splash screen inside that executable cannot cover this interval. Changing
installation compression or adding an `InitializeWizard` splash does not fix
this pre-execution delay.

For a small setup executable with companion payload files, build with:

```powershell
.\scripts\build-installer.ps1 -SkipAppBuild -SplitPayload
```

For a bundled edition, also pass the same `-BundleExternalTools` and
`-VideOCRVariant` options used to build the existing application. Alternatively,
omit `-SkipAppBuild` and supply the normal application build arguments.

The build prints a unique fast-start folder under `release`. Distribute the
entire folder: the setup EXE, every `.bin` file, and `START-HERE.txt`. If you ZIP
the folder, users must extract everything before opening the EXE. Each binary
has a SHA-256 sidecar. Signing options still apply to the setup executable.

This moves the large payload outside the executable Windows checks at launch,
allowing the language dialog and setup wizard to appear sooner. The wizard
shows progress during installation. It cannot guarantee immediate UI before
Windows security checks finish. No fake percentage or extra confirmation is
shown at startup.

Version 0.5.3 introduced CPU and CUDA fast-start ZIP packages. Version 0.6.0
defaults to a small web EXE that downloads and installs the app and CPU OCR, with optional GPU OCR downloaded in the app; see [runtime downloads](runtime-downloads.md).
The full offline ZIPs remain available through `-OfflineInstallers`.
The offline build includes all payload files and instructions,
checks the GitHub size limit, and records the ZIP checksums in the release
manifest. Staging validates the internal checksums and the setup EXE signature.
Standalone builds without `-SplitPayload` still produce single-file installers.

Validate on a clean Windows machine with the actual CPU/GPU payload: measure
double-click to language dialog, confirm installation progress and successful
launch, and test the missing-payload error. Compare first launches from the same
local drive under the same security settings; a tiny compile fixture cannot
establish real startup speed.

Reference: [Inno Setup's guidance on large-installer startup delays](https://jrsoftware.org/ishelp/topic_setup_usesetupldr.htm).
