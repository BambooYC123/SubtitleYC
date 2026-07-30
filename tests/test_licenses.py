from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class LicenseBundleTests(unittest.TestCase):
    def test_required_release_notices_exist(self) -> None:
        required = (
            "LICENSE",
            "CONTRIBUTING.md",
            "PRIVACY.md",
            "SECURITY.md",
            "THIRD-PARTY-NOTICES.txt",
            "licenses/VideOCR-MIT.txt",
            "licenses/yt-dlp-Unlicense.txt",
            "licenses/GPL-3.0.txt",
            "licenses/LGPL-3.0.txt",
        )
        missing = [path for path in required if not (ROOT / path).is_file()]
        self.assertEqual([], missing)

    def test_third_party_notice_names_core_components(self) -> None:
        notice = (ROOT / "THIRD-PARTY-NOTICES.txt").read_text(encoding="utf-8")
        for component in ("VideOCR", "yt-dlp", "FFmpeg", "PySide6"):
            with self.subTest(component=component):
                self.assertIn(component, notice)

    def test_project_uses_standard_mit_license(self) -> None:
        license_text = (ROOT / "LICENSE").read_text(encoding="utf-8")
        self.assertIn("MIT License", license_text)
        self.assertIn("Copyright (c) 2026 EricYC123", license_text)
        self.assertIn("Permission is hereby granted, free of charge", license_text)
        self.assertIn('THE SOFTWARE IS PROVIDED "AS IS"', license_text)
        self.assertNotIn("End User License Agreement", license_text)

    def test_project_metadata_declares_mit(self) -> None:
        metadata = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
        self.assertIn('license = { file = "LICENSE" }', metadata)
        self.assertIn('"License :: OSI Approved :: MIT License"', metadata)

    def test_notices_match_pinned_runtime_versions(self) -> None:
        notice = (ROOT / "THIRD-PARTY-NOTICES.txt").read_text(encoding="utf-8")
        requirements = (ROOT / "requirements-release.txt").read_text(encoding="utf-8")
        self.assertIn("Version used by the current Windows build: 6.11.1", notice)
        self.assertIn("pyside6==6.11.1", requirements.lower())
        self.assertIn("Version bundled by the current Windows build: 2026.7.4", notice)
        self.assertIn("yt-dlp==2026.7.4", requirements)
        self.assertIn("Gyan FFmpeg 8.1.2 full shared build", notice)


if __name__ == "__main__":
    unittest.main()