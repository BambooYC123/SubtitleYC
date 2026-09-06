import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from subtitleyc.atomic_files import save_text


class AtomicSaveTests(unittest.TestCase):
    def test_keeps_previous_successful_save(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "captions.srt"
            save_text(path, "first 字幕")
            save_text(path, "second")
            self.assertEqual(path.read_text(encoding="utf-8"), "second")
            self.assertEqual(path.with_suffix(".srt.bak").read_text(encoding="utf-8"), "first 字幕")
            save_text(path, "third")
            self.assertEqual(path.with_suffix(".srt.bak").read_text(), "second")

    def test_failed_replacement_preserves_original_and_removes_temporary(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "captions.srt"
            save_text(path, "original")
            import os
            replace = os.replace

            def fail_final(source, target):
                if Path(target) == path:
                    raise OSError("disk error")
                replace(source, target)

            with patch("subtitleyc.atomic_files.os.replace", side_effect=fail_final):
                with self.assertRaises(OSError):
                    save_text(path, "new")
            self.assertEqual(path.read_text(), "original")
            self.assertEqual(path.with_suffix(".srt.bak").read_text(), "original")
            self.assertEqual(list(Path(directory).glob("*.tmp")), [])
