from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
INSTALLER_SCRIPT = ROOT / "installer" / "SubtitleYC.iss"
INSTALLER_INFO = ROOT / "installer" / "before-install.txt"


class InstallerLayoutTests(unittest.TestCase):
    def test_installer_defaults_to_64_bit_program_files(self) -> None:
        script = INSTALLER_SCRIPT.read_text(encoding="utf-8")
        self.assertIn(r"DefaultDirName={code:GetDefaultDirName}", script)
        self.assertIn(r"ExpandConstant('{autopf}\SubtitleYC')", script)
        self.assertIn("ArchitecturesInstallIn64BitMode=x64compatible", script)
        self.assertIn("PrivilegesRequired=admin", script)
        self.assertIn("UsePreviousAppDir=no", script)

    def test_installer_safely_migrates_previous_installation(self) -> None:
        script = INSTALLER_SCRIPT.read_text(encoding="utf-8")
        self.assertIn("function PrepareToInstall", script)
        self.assertIn("UninstallString", script)
        self.assertIn("/VERYSILENT /SUPPRESSMSGBOXES /NORESTART", script)
        self.assertNotIn(r'Type: filesandordirs; Name: "{localappdata}\Programs\SubtitleYC"', script)

    def test_desktop_and_start_menu_shortcuts_are_unconditional(self) -> None:
        script = INSTALLER_SCRIPT.read_text(encoding="utf-8")
        desktop_line = next(line for line in script.splitlines() if r"{autodesktop}\SubtitleYC" in line)
        self.assertNotIn("Tasks:", desktop_line)
        self.assertIn(r"{group}\SubtitleYC", script)
        self.assertNotIn("[Tasks]", script)

    def test_installer_explains_application_and_workspace_locations(self) -> None:
        info = INSTALLER_INFO.read_text(encoding="utf-8")
        self.assertIn(r"%ProgramFiles%\SubtitleYC", info)
        self.assertIn(r"%LOCALAPPDATA%\SubtitleYC\workspace", info)

    def test_installer_displays_open_source_license(self) -> None:
        script = INSTALLER_SCRIPT.read_text(encoding="utf-8")
        self.assertIn(r"LicenseFile=..\LICENSE", script)
        self.assertNotIn("EULA", script)

    def test_installer_keeps_numeric_and_visible_beta_versions_separate(self) -> None:
        script = INSTALLER_SCRIPT.read_text(encoding="utf-8")
        build_script = (ROOT / "scripts" / "build-installer.ps1").read_text(encoding="utf-8")
        self.assertIn("AppVersion={#AppDisplayVersion}", script)
        self.assertIn("VersionInfoVersion={#AppVersion}", script)
        self.assertIn('"-ReleaseLabel", $ReleaseLabel', build_script)
        self.assertIn("/DAppDisplayVersion=$ReleaseLabel", build_script)

    def test_installer_build_can_skip_the_redundant_portable_zip(self) -> None:
        installer = INSTALLER_SCRIPT.read_text(encoding="utf-8")
        build_script = (ROOT / "scripts" / "build-installer.ps1").read_text(encoding="utf-8")
        self.assertNotIn("DiskSpanning=yes", installer)
        self.assertNotIn('"/DSplitPayload=1"', build_script)
        self.assertIn("-SkipPortableZip", build_script)

    def test_release_build_records_ffmpeg_provenance(self) -> None:
        build_script = (ROOT / "scripts" / "build-windows.ps1").read_text(encoding="utf-8")
        self.assertIn('"BUILD-INFO.txt"', build_script)
        self.assertIn("$ffmpegSource -version", build_script)
        self.assertIn("ffmpeg SHA-256", build_script)

    def test_public_release_build_has_one_run_manifest_and_no_portable_zips(self) -> None:
        build_script = (ROOT / "scripts" / "build-public-releases.ps1").read_text(encoding="utf-8")
        self.assertIn("PUBLIC-BUILD-MANIFEST.json", build_script)
        self.assertIn("source_fingerprint_sha256", build_script)
        self.assertIn("release_label = $ReleaseLabel", build_script)
        self.assertIn('"-SkipPortableZip"', build_script)


if __name__ == "__main__":
    unittest.main()