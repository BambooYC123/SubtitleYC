"""Regression tests for defects found in the 0.6.0 code review."""

import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock
from unittest.mock import patch

_DATA_DIR = tempfile.mkdtemp(prefix="subtitleyc-review-tests-")
os.environ.setdefault("SUBTITLEYC_DATA_DIR", _DATA_DIR)

from subtitleyc import main  # noqa: E402
from subtitleyc.process import stop_process_tree  # noqa: E402
from subtitleyc.srt import (  # noqa: E402
    SubtitleCue,
    cues_to_ass,
    cues_to_srt,
    cues_to_txt,
    parse_ass,
    parse_srt,
)
from subtitleyc.videocr_cli import _cli_preference, count_srt_cues  # noqa: E402


class SubtitleExportTests(unittest.TestCase):
    STYLED = SubtitleCue(1.0, 2.0, '<b>Hi</b> <font color="#ff0000">red</font>\n<i>x</i> {y}')

    def test_srt_numbering_has_no_gaps_when_blank_cues_are_skipped(self) -> None:
        text = cues_to_srt([SubtitleCue(0, 1, "a"), SubtitleCue(1, 2, "  "), SubtitleCue(2, 3, "c")])
        self.assertEqual([line for line in text.splitlines() if line.isdigit()], ["1", "2"])

    def test_txt_export_drops_editor_styling_markup(self) -> None:
        self.assertEqual(cues_to_txt([self.STYLED]), "Hi red x {y}\n")

    def test_ass_export_translates_styling_and_blocks_override_injection(self) -> None:
        dialogue = cues_to_ass([self.STYLED]).splitlines()[-1]
        self.assertTrue(dialogue.endswith(r"{\b1}Hi{\b0} {\c&H0000FF&}red{\c}\N{\i1}x{\i0} (y)"))
        self.assertNotIn("<b>", dialogue)

    def test_ass_styling_round_trips_through_the_editor_markup(self) -> None:
        cue = parse_ass(cues_to_ass([self.STYLED]))[0]
        self.assertEqual(cue.text, '<b>Hi</b> <font color="#ff0000">red</font>\n<i>x</i> (y)')

    def test_webvtt_short_timestamps_and_inline_tags_are_parsed(self) -> None:
        cues = parse_srt(
            "WEBVTT\n\nNOTE made by a site\n\n"
            "00:01.000 --> 00:04.500 align:start\n<00:00:01.500><c> hello</c> world\n"
        )
        self.assertEqual(cues, [SubtitleCue(1.0, 4.5, "hello world")])

    def test_cue_count_ignores_numeric_subtitle_text(self) -> None:
        self.assertEqual(count_srt_cues("1\n00:00:01,000 --> 00:00:02,000\n2024\n"), 1)


class VideOCRLookupTests(unittest.TestCase):
    def test_matching_build_and_newest_version_win(self) -> None:
        paths = [
            Path(r"C:\VideOCR\videocr-cli-GPU-v1.5.1\videocr-cli.exe"),
            Path(r"C:\VideOCR\videocr-cli-CPU-v1.4.0\videocr-cli.exe"),
            Path(r"C:\VideOCR\videocr-cli-CPU-v1.10.0\videocr-cli.exe"),
        ]
        cpu_first = sorted(paths, key=lambda path: _cli_preference(path, False))
        self.assertIn("CPU-v1.10.0", str(cpu_first[0]))
        gpu_first = sorted(paths, key=lambda path: _cli_preference(path, True))
        self.assertIn("GPU-v1.5.1", str(gpu_first[0]))


class SettingsRobustnessTests(unittest.TestCase):
    def test_one_invalid_saved_value_does_not_discard_the_rest(self) -> None:
        settings = main._validated_settings({"confidence": 999, "ui_language": "zh-CN", "retired_option": True})
        self.assertEqual(settings.confidence, main.AppSettings().confidence)
        self.assertEqual(settings.ui_language, "zh-CN")

    def test_settings_file_with_bad_value_still_loads(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "settings.json"
            path.write_text(json.dumps({"theme": "neon", "merge_gap": 0.5}), encoding="utf-8")
            with mock.patch.object(main, "SETTINGS_PATH", path), mock.patch.object(
                main, "_consume_installer_ui_language", return_value=None
            ):
                settings = main._load_settings()
        self.assertEqual(settings.theme, "dark")
        self.assertEqual(settings.merge_gap, 0.5)


class JobHistoryTests(unittest.TestCase):
    def test_finished_jobs_are_bounded_and_active_jobs_survive(self) -> None:
        with mock.patch.object(main, "jobs", {}), mock.patch.object(main, "job_cancel_events", {}), mock.patch.object(
            main, "FINISHED_JOB_HISTORY", 3
        ):
            running = main._create_job("ocr")
            for _ in range(6):
                main._set_job(main._create_job("download").id, status="complete")
            main._create_job("ocr")
            finished = [job for job in main.jobs.values() if job.status == "complete"]
            self.assertEqual(len(finished), 3)
            self.assertIn(running.id, main.jobs)


class FailedOcrKeepsSubtitlesTests(unittest.TestCase):
    def test_failed_run_leaves_existing_subtitle_file_untouched(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            results = Path(folder) / "results"
            runtime = Path(folder) / "runtime"
            results.mkdir()
            runtime.mkdir()
            session = main.VideoSession(
                id="a" * 32,
                video_path=str(Path(folder) / "clip.mp4"),
                original_name="clip.mp4",
                source_type="local",
                metadata={"fps": 25.0},
                preview_path="",
            )
            written: list[Path] = []

            def failing_cli(_video: Path, output_path: Path, *_args: object, **_kwargs: object) -> str:
                written.append(output_path)
                raise RuntimeError("VideOCR CLI failed with exit code 1.")

            with mock.patch.object(main, "RESULTS_DIR", results), mock.patch.object(
                main, "VIDEOCR_RUNTIME_DIR", runtime
            ), mock.patch.object(main, "sessions", {session.id: session}), mock.patch.object(
                main, "jobs", {}
            ), mock.patch.object(main, "find_videocr_cli", return_value="videocr-cli.exe"), mock.patch.object(
                main, "run_videocr_cli", side_effect=failing_cli
            ):
                existing = main._subtitle_storage_path(session, "srt")
                existing.write_text("1\n00:00:01,000 --> 00:00:02,000\nedited by hand\n", encoding="utf-8")
                session.srt_path = str(existing)
                job = main._create_job("ocr")
                request = main.OCRRequest(crop=main.CropRequest(x=0, y=0, width=10, height=10))
                main._run_ocr_job(job.id, session.id, request)

                self.assertEqual(main.jobs[job.id].status, "failed")
                self.assertIn("edited by hand", existing.read_text(encoding="utf-8"))
                self.assertNotEqual(written[0], existing)
                self.assertEqual(list(runtime.glob("ocr-*.srt")), [])


class InstallerTextTests(unittest.TestCase):
    def test_chinese_installer_page_is_real_chinese_with_a_bom(self) -> None:
        raw = (Path(__file__).resolve().parents[1] / "installer" / "before-install.zh-CN.txt").read_bytes()
        self.assertTrue(raw.startswith(b"\xef\xbb\xbf"), "Inno Setup needs a UTF-8 BOM to read this page")
        text = raw.decode("utf-8-sig")
        self.assertNotIn("???", text)
        self.assertGreater(sum("一" <= char <= "鿿" for char in text), 200)


class ShutdownTests(unittest.TestCase):
    def test_closing_the_app_cancels_active_jobs_and_stops_their_processes(self) -> None:
        process = mock.Mock()
        fake_executor = mock.Mock()
        with mock.patch.object(main, "jobs", {}), mock.patch.object(main, "job_cancel_events", {}), mock.patch.object(
            main, "job_processes", {}
        ), mock.patch.object(main, "executor", fake_executor), mock.patch.object(
            main, "stop_process_tree"
        ) as stop_tree:
            job = main._create_job("ocr")
            main._set_job(job.id, status="running")
            main._register_job_process(job.id, process)

            main.stop_all_jobs()

            self.assertTrue(main._cancel_requested(job.id))
            stop_tree.assert_called_once_with(process)
            fake_executor.shutdown.assert_called_once_with(wait=False, cancel_futures=True)


@unittest.skipUnless(sys.platform == "win32", "Windows process-tree behaviour")
class ProcessTreeTests(unittest.TestCase):
    def test_cancel_stops_grandchild_processes(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            pid_file = Path(folder) / "child.pid"
            script = (
                "import subprocess, sys, time\n"
                "child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(120)'])\n"
                f"open(r'{pid_file}', 'w').write(str(child.pid))\n"
                "time.sleep(120)\n"
            )
            parent = subprocess.Popen([sys.executable, "-c", script])
            try:
                deadline = time.monotonic() + 15
                while not pid_file.exists() or not pid_file.read_text().strip():
                    self.assertLess(time.monotonic(), deadline, "child process did not start")
                    time.sleep(0.05)
                child_pid = int(pid_file.read_text())

                stop_process_tree(parent)

                self.assertIsNotNone(parent.poll())
                deadline = time.monotonic() + 10
                while self._pid_running(child_pid):
                    self.assertLess(time.monotonic(), deadline, "grandchild survived the cancel")
                    time.sleep(0.1)
            finally:
                if parent.poll() is None:
                    parent.kill()

    @staticmethod
    def _pid_running(pid: int) -> bool:
        listing = subprocess.run(
            ["tasklist", "/FI", f"PID eq {pid}", "/NH"],
            capture_output=True,
            text=True,
            check=False,
        ).stdout
        return str(pid) in listing


if __name__ == "__main__":
    unittest.main()


class GpuPackageTests(unittest.TestCase):
    """The GPU OCR package crashes in CPU mode, so it must always be run on the GPU."""

    def test_gpu_build_always_runs_on_the_gpu(self) -> None:
        from subtitleyc.videocr_cli import VideOCRCliSettings, is_gpu_build, settings_for_cli

        gpu_cli = r"C:\Users\someone\AppData\Local\SubtitleYC\runtimes\gpu-cuda-12.9-3c8e\videocr-cli-GPU-v1.5.1-CUDA-12.9\videocr-cli.exe"
        cpu_cli = r"C:\Users\gpufan\AppData\Local\SubtitleYC\runtimes\cpu-1a2b\videocr-cli-CPU-v1.5.1\videocr-cli.exe"
        settings = VideOCRCliSettings(crop_x=0, crop_y=0, crop_width=10, crop_height=10, use_gpu=False)

        self.assertTrue(is_gpu_build(gpu_cli))
        self.assertFalse(is_gpu_build(cpu_cli), "a user name containing 'gpu' is not a GPU build")
        self.assertFalse(is_gpu_build(None))
        self.assertTrue(settings_for_cli(gpu_cli, settings).use_gpu)
        self.assertFalse(settings_for_cli(cpu_cli, settings).use_gpu)
        self.assertFalse(settings.use_gpu, "the caller's settings are not modified")


class PastedLinkTests(unittest.TestCase):
    def test_link_is_taken_out_of_share_text_and_rednote_host_is_mapped(self) -> None:
        from subtitleyc.security import clean_video_url

        self.assertEqual(clean_video_url("  https://youtu.be/jNQXAC9IVRw  "), "https://youtu.be/jNQXAC9IVRw")
        self.assertEqual(
            clean_video_url("【标题-哔哩哔哩】 https://b23.tv/AbC12de 复制后打开"),
            "https://b23.tv/AbC12de",
        )
        self.assertEqual(
            clean_video_url("86 看看这个 http://xhslink.com/a/AbCdEf，复制本条信息"),
            "http://xhslink.com/a/AbCdEf",
        )
        self.assertEqual(
            clean_video_url("https://www.rednote.com/explore/674051740000000007027a15?xsec_token=abc=&xsec_source=pc_feed"),
            "https://www.xiaohongshu.com/explore/674051740000000007027a15?xsec_token=abc=&xsec_source=pc_feed",
        )
        # Anything that is not a Rednote note page is left alone.
        self.assertEqual(clean_video_url("https://www.rednote.com/user/profile/123"), "https://www.rednote.com/user/profile/123")
        self.assertEqual(clean_video_url("https://x.com/a/status/1?s=20"), "https://x.com/a/status/1?s=20")
        self.assertEqual(clean_video_url("not a link"), "not a link")


class GpuSetupChoiceTests(unittest.TestCase):
    """Setup records whether GPU OCR was wanted; the app acts on it at first launch."""

    def test_onboarding_decision(self) -> None:
        from subtitleyc.main import onboarding_decision

        supported = {"installed": False, "compatibility": {"compatible": True}}
        unsupported = {"installed": False, "compatibility": {"compatible": False}}
        installed = {"installed": True, "compatibility": {"compatible": True}}

        # Box ticked on a supported PC: download by itself, no panel.
        self.assertEqual(
            onboarding_decision(seen=True, auto_requested=True, gpu=supported, ocr_available=True),
            {"auto_gpu_download": True, "show_welcome": False},
        )
        # Ticked, but the card is no longer supported or the package is already there: nothing to do.
        for gpu in (unsupported, installed, None):
            self.assertFalse(onboarding_decision(seen=True, auto_requested=True, gpu=gpu, ocr_available=True)["auto_gpu_download"])
        # No answer from setup (portable or older installer): offer once on a supported PC only.
        self.assertTrue(onboarding_decision(seen=False, auto_requested=False, gpu=supported, ocr_available=True)["show_welcome"])
        self.assertFalse(onboarding_decision(seen=False, auto_requested=False, gpu=unsupported, ocr_available=True)["show_welcome"])
        self.assertFalse(onboarding_decision(seen=True, auto_requested=False, gpu=supported, ocr_available=True)["show_welcome"])
        # No OCR engine at all: the panel is the way to get one, whatever the card.
        self.assertTrue(onboarding_decision(seen=False, auto_requested=False, gpu=unsupported, ocr_available=False)["show_welcome"])

    def test_installer_choice_is_consumed_once_and_pause_cancels_auto_download(self) -> None:
        from fastapi.testclient import TestClient

        with tempfile.TemporaryDirectory() as folder:
            data_dir = Path(folder)
            with patch.object(main, "DATA_DIR", data_dir), patch.object(
                main, "_read_installer_gpu_choice", return_value=("0.7.1", "1")
            ):
                main._consume_installer_gpu_choice()
                self.assertTrue((data_dir / ".gpu-ocr-auto").is_file())
                self.assertTrue((data_dir / ".ocr-setup-seen").is_file())
                # The same install is not acted on twice, so a later pause sticks.
                client = TestClient(main.app)
                response = client.post("/api/runtimes/pause", headers={"X-SubtitleYC-Token": main.API_TOKEN})
                self.assertEqual(response.status_code, 200)
                self.assertFalse((data_dir / ".gpu-ocr-auto").exists())
                main._consume_installer_gpu_choice()
                self.assertFalse((data_dir / ".gpu-ocr-auto").exists())
            with patch.object(main, "DATA_DIR", data_dir), patch.object(
                main, "_read_installer_gpu_choice", return_value=("0.7.2", "0")
            ):
                main._consume_installer_gpu_choice()
                self.assertFalse((data_dir / ".gpu-ocr-auto").exists())
