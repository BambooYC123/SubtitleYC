import json
import logging
import shutil
import tempfile
import uuid
import unittest
from pathlib import Path

from fastapi import HTTPException
from fastapi.testclient import TestClient

from subtitleyc import __release__, __version__
from subtitleyc.logs import clear_log_entries, configure_logging, get_log_entries, log_event
from subtitleyc.main import (
    API_TOKEN,
    AppSettings,
    CropRequest,
    OCRRequest,
    RESULTS_DIR,
    SETTINGS_PATH,
    VideoSession,
    _default_settings,
    _directory_stats,
    create_ocr_job,
    _download_format,
    _download_headers,
    _downloaded_video_from_info,
    _resolve_download_dir,
    _safe_clear_directory_contents,
    _subtitle_storage_path,
    app,
    sessions,
    state_lock,
)
from subtitleyc.srt import SubtitleCue, adjust_cue_timing, cues_to_ass, cues_to_srt, cues_to_txt, format_timestamp, parse_ass, parse_srt
from subtitleyc.videocr_cli import VideOCRCliSettings, _build_args, count_srt_cues, find_videocr_cli, map_language, seconds_to_cli_time

def authenticated_client() -> TestClient:
    return TestClient(app, headers={"X-SubtitleYC-Token": API_TOKEN})


class TestSrt(unittest.TestCase):
    def test_system_status_reports_exact_release(self):
        self.assertEqual(__version__, "0.5.1")
        self.assertEqual(__release__, "0.5.1")
        response = authenticated_client().get("/api/system")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["release_label"], "0.5.1")

    def test_download_format_limits_resolution(self):
        self.assertIn("height<=720", _download_format(720))
        self.assertNotIn("height<=", _download_format(None))

    def test_download_format_prefers_known_bilibili_streams(self):
        download_format = _download_format(1080, "https://www.bilibili.com/video/BV1AW98BoE6a")
        self.assertTrue(download_format.startswith("30080+30280/"))
        self.assertIn("30064+30280", download_format)
        self.assertIn("30016+30280", download_format)
        self.assertIn("height<=1080", download_format)

    def test_download_headers_include_bilibili_referer(self):
        headers = _download_headers("https://www.bilibili.com/video/BV1AW98BoE6a")
        self.assertEqual(headers["Referer"], "https://www.bilibili.com/")
        self.assertEqual(headers["Origin"], "https://www.bilibili.com")
        self.assertIn("Chrome", headers["User-Agent"])


    def test_app_settings_defaults_are_serializable(self):
        settings = AppSettings().model_dump()

        self.assertEqual(settings["default_resolution"], "1080")
        self.assertEqual(settings["default_language"], "eng+chi_sim")
        self.assertEqual(settings["default_subtitle_format"], "srt")
        self.assertTrue(settings["use_server_model"])
        self.assertFalse(settings["use_gpu"])

    def test_gpu_release_marker_enables_gpu_on_first_run(self):
        with tempfile.TemporaryDirectory() as root:
            tools = Path(root) / "tools"
            tools.mkdir()
            (tools / "videocr-build.json").write_text(
                json.dumps({"variant": "gpu-cuda-12.9", "gpu_default": True}),
                encoding="utf-8",
            )
            with unittest.mock.patch("subtitleyc.main.RUNTIME_ROOT", Path(root)):
                defaults = _default_settings()
        self.assertTrue(defaults["use_gpu"])

    def test_cpu_release_marker_keeps_gpu_disabled_on_first_run(self):
        with tempfile.TemporaryDirectory() as root:
            tools = Path(root) / "tools"
            tools.mkdir()
            (tools / "videocr-build.json").write_text(
                json.dumps({"variant": "cpu", "gpu_default": False}),
                encoding="utf-8",
            )
            with unittest.mock.patch("subtitleyc.main.RUNTIME_ROOT", Path(root)):
                defaults = _default_settings()
        self.assertFalse(defaults["use_gpu"])

    def test_settings_api_persists_to_settings_file(self):
        original = SETTINGS_PATH.read_text(encoding="utf-8") if SETTINGS_PATH.is_file() else None
        client = authenticated_client()
        try:
            response = client.get("/api/settings")
            self.assertEqual(response.status_code, 200)
            settings = response.json()["settings"]
            settings["confidence"] = 73 if settings.get("confidence") != 73 else 74
            settings["default_subtitle_format"] = "ass"
            settings["use_gpu"] = not settings.get("use_gpu", False)

            response = client.put("/api/settings", json=settings)
            self.assertEqual(response.status_code, 200)
            self.assertTrue(SETTINGS_PATH.is_file())

            saved = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
            self.assertEqual(saved["confidence"], settings["confidence"])
            self.assertEqual(saved["default_subtitle_format"], "ass")
            self.assertEqual(saved["use_gpu"], settings["use_gpu"])
            self.assertEqual(client.get("/api/settings").json()["settings"]["default_subtitle_format"], "ass")
        finally:
            if original is None:
                SETTINGS_PATH.unlink(missing_ok=True)
            else:
                SETTINGS_PATH.write_text(original, encoding="utf-8")

    def test_resolve_download_dir_creates_custom_folder(self):
        with tempfile.TemporaryDirectory() as root:
            target = Path(root) / "video downloads"
            self.assertEqual(_resolve_download_dir("job-id", str(target)), target)
            self.assertTrue(target.is_dir())

    def test_downloaded_video_from_info_prefers_reported_filepath(self):
        with tempfile.TemporaryDirectory() as root:
            video_path = Path(root) / "downloaded.mp4"
            video_path.write_bytes(b"placeholder")
            info = {"requested_downloads": [{"filepath": str(video_path)}]}
            self.assertEqual(_downloaded_video_from_info(info), video_path)


    def test_storage_helpers_measure_and_clear_directory(self):
        target = RESULTS_DIR / f"test-storage-{uuid.uuid4().hex}"
        nested = target / "nested"
        try:
            nested.mkdir(parents=True)
            (target / "a.txt").write_bytes(b"abc")
            (nested / "b.txt").write_bytes(b"defg")

            stats = _directory_stats(target)
            self.assertEqual(stats["files"], 2)
            self.assertEqual(stats["bytes"], 7)

            _safe_clear_directory_contents(target)
            self.assertEqual(list(target.iterdir()), [])
        finally:
            shutil.rmtree(target, ignore_errors=True)

    def test_subtitle_editor_api_round_trips_ass_output(self):
        session_id = f"test-{uuid.uuid4().hex}"
        session = VideoSession(
            id=session_id,
            video_path="",
            original_name="Demo.mp4",
            source_type="test",
            metadata={"duration": 5, "fps": 24, "width": 1920, "height": 1080},
            preview_path="",
        )
        source = _subtitle_storage_path(session, "srt")
        ass_output = _subtitle_storage_path(session, "ass")
        with state_lock:
            sessions[session_id] = session
        try:
            client = authenticated_client()
            response = client.put(
                f"/api/videos/{session_id}/subtitles",
                json={
                    "subtitle_format": "ass",
                    "cues": [
                        {"start_seconds": 1.0, "end_seconds": 2.0, "text": "Hello"},
                        {"start_seconds": 2.5, "end_seconds": 3.0, "text": "World"},
                    ],
                },
            )
            self.assertEqual(response.status_code, 200)
            payload = response.json()
            self.assertEqual(payload["cue_count"], 2)
            self.assertEqual(payload["subtitle_format"], "ass")
            self.assertTrue(ass_output.is_file())

            response = client.get(f"/api/videos/{session_id}/subtitles")
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()["cues"][0]["text"], "Hello")
        finally:
            with state_lock:
                sessions.pop(session_id, None)
            source.unlink(missing_ok=True)
            ass_output.unlink(missing_ok=True)

    def test_subtitle_import_api_loads_ass_file(self):
        session_id = f"test-{uuid.uuid4().hex}"
        session = VideoSession(
            id=session_id,
            video_path="",
            original_name="Imported.mp4",
            source_type="test",
            metadata={"duration": 5, "fps": 24, "width": 1920, "height": 1080},
            preview_path="",
        )
        source = _subtitle_storage_path(session, "srt")
        ass_output = _subtitle_storage_path(session, "ass")
        with state_lock:
            sessions[session_id] = session
        try:
            client = authenticated_client()
            ass_text = cues_to_ass(
                [SubtitleCue(start_seconds=1.0, end_seconds=1.5, text="Loaded\nLine")],
                title="Imported",
            )
            response = client.post(
                f"/api/videos/{session_id}/subtitles/import",
                files={"file": ("loaded.ass", ass_text.encode("utf-8"), "text/plain")},
            )

            self.assertEqual(response.status_code, 200)
            payload = response.json()
            self.assertEqual(payload["cue_count"], 1)
            self.assertEqual(payload["subtitle_format"], "ass")
            self.assertEqual(payload["cues"][0]["text"], "Loaded\nLine")
            self.assertTrue(source.is_file())
            self.assertTrue(ass_output.is_file())
        finally:
            with state_lock:
                sessions.pop(session_id, None)
            source.unlink(missing_ok=True)
            ass_output.unlink(missing_ok=True)
    def test_format_timestamp_rounds_to_milliseconds(self):
        self.assertEqual(format_timestamp(3661.2345), "01:01:01,234")

    def test_videocr_language_mapping_uses_paddle_chinese_for_mixed_subtitles(self):
        self.assertEqual(map_language("eng"), "en")
        self.assertEqual(map_language("chi_sim"), "ch")
        self.assertEqual(map_language("eng+chi_sim"), "ch")
        self.assertEqual(map_language("chi_tra"), "chinese_cht")
        self.assertEqual(map_language("eng+chi_tra"), "chinese_cht")

    def test_videocr_language_mapping_passes_supported_models_through(self):
        expected = {
            "japan",
            "korean",
            "vi",
            "th",
            "id",
            "ms",
            "tl",
            "hi",
            "mr",
            "ne",
            "ta",
            "te",
            "ar",
            "fa",
            "ur",
            "ug",
            "tr",
            "kk",
            "mn",
            "es",
            "fr",
            "de",
            "pt",
            "it",
            "ru",
            "uk",
        }
        self.assertEqual({map_language(language) for language in expected}, expected)

    def test_videocr_language_mapping_rejects_unknown_models(self):
        with self.assertRaisesRegex(ValueError, "Unsupported VideOCR language"):
            map_language("not-a-language")

    def test_videocr_cli_finder_prefers_gpu_build_when_requested(self):
        with tempfile.TemporaryDirectory() as root:
            tools = Path(root) / "tools"
            cpu = tools / "videocr-cli-CPU-v1.4.0" / "videocr-cli.exe"
            gpu = tools / "videocr-cli-GPU-v1.4.0" / "videocr-cli.exe"
            cpu.parent.mkdir(parents=True)
            gpu.parent.mkdir(parents=True)
            cpu.touch()
            gpu.touch()
            with unittest.mock.patch("subtitleyc.videocr_cli._runtime_root", return_value=Path(root)), unittest.mock.patch(
                "subtitleyc.videocr_cli._CLI_CANDIDATES", ()
            ):
                self.assertEqual(find_videocr_cli(prefer_gpu=True), str(gpu))
                self.assertEqual(find_videocr_cli(prefer_gpu=False), str(cpu))

    def test_videocr_cli_finder_does_not_use_cpu_build_for_gpu_mode(self):
        with tempfile.TemporaryDirectory() as root:
            cpu = Path(root) / "tools" / "videocr-cli-CPU-v1.4.0" / "videocr-cli.exe"
            cpu.parent.mkdir(parents=True)
            cpu.touch()
            with unittest.mock.patch("subtitleyc.videocr_cli._runtime_root", return_value=Path(root)), unittest.mock.patch(
                "subtitleyc.videocr_cli._CLI_CANDIDATES", ()
            ), unittest.mock.patch.dict("os.environ", {"VIDEOCR_CLI": str(cpu)}):
                self.assertIsNone(find_videocr_cli(prefer_gpu=True))
                self.assertEqual(find_videocr_cli(prefer_gpu=False), str(cpu))

    def test_ocr_gpu_request_is_rejected_before_job_is_created_when_unavailable(self):
        request = OCRRequest(
            crop=CropRequest(x=0, y=0, width=1280, height=200),
            use_gpu=True,
        )
        with unittest.mock.patch("subtitleyc.main._get_session"), unittest.mock.patch(
            "subtitleyc.main.find_videocr_cli", return_value=None
        ):
            with self.assertRaises(HTTPException) as raised:
                create_ocr_job("test-session", request)
        self.assertEqual(raised.exception.status_code, 409)
        self.assertIn("GPU build", str(raised.exception.detail))

    def test_videocr_gpu_setting_is_forwarded_to_cli(self):
        settings = VideOCRCliSettings(
            crop_x=0,
            crop_y=0,
            crop_width=1280,
            crop_height=200,
            use_gpu=True,
        )
        args = _build_args(Path("video.mp4"), Path("output.srt"), settings)
        gpu_index = args.index("--use_gpu")
        self.assertEqual(args[gpu_index + 1], "true")

    def test_videocr_v151_args_do_not_send_removed_dual_zone_flag(self):
        settings = VideOCRCliSettings(
            crop_x=0,
            crop_y=0,
            crop_width=1280,
            crop_height=200,
            use_dual_zone=False,
        )
        args = _build_args(Path("video.mp4"), Path("output.srt"), settings)
        self.assertNotIn("--use_dual_zone", args)

    def test_videocr_helpers_format_time_and_count_cues(self):
        self.assertEqual(seconds_to_cli_time(65), "1:05")
        self.assertEqual(seconds_to_cli_time(3661), "1:01:01")
        self.assertEqual(
            count_srt_cues("1\n00:00:00,000 --> 00:00:01,000\nA\n\n2\n00:00:02,000 --> 00:00:03,000\nB\n"),
            2,
        )

    def test_cues_to_srt_writes_numbered_blocks(self):
        srt = cues_to_srt(
            [
                SubtitleCue(start_seconds=0, end_seconds=1.25, text="Hello"),
                SubtitleCue(start_seconds=2, end_seconds=3, text="World"),
            ]
        )

        self.assertIn("1\n00:00:00,000 --> 00:00:01,250\nHello", srt)
        self.assertIn("2\n00:00:02,000 --> 00:00:03,000\nWorld", srt)

    def test_srt_round_trip_preserves_inline_subtitle_styles(self):
        styled = '<b>Bold</b> <i>italic</i> <u>underlined</u> <font color="#14b8a6">teal</font>'

        srt = cues_to_srt([SubtitleCue(start_seconds=0, end_seconds=2, text=styled)])
        parsed = parse_srt(srt)

        self.assertEqual(parsed[0].text, styled)

    def test_adjust_cue_timing_snaps_then_preserves_subframe_offset(self):
        adjusted = adjust_cue_timing(
            [SubtitleCue(start_seconds=1.04, end_seconds=1.16, text="A")],
            offset_seconds=0.04,
            frame_seconds=0.1,
        )

        self.assertAlmostEqual(adjusted[0].start_seconds, 1.04)
        self.assertAlmostEqual(adjusted[0].end_seconds, 1.24)
    def test_log_buffer_filters_and_clears_entries(self):
        with tempfile.TemporaryDirectory() as root:
            try:
                configure_logging(Path(root))
                clear_log_entries()
                log_event("download started", category="download", job_id="abc123")
                log_event("ocr failed", category="ocr", level=logging.ERROR)

                self.assertEqual(len(get_log_entries()), 2)
                self.assertEqual(get_log_entries(category="download")[0]["message"], "download started")
                self.assertEqual(get_log_entries(level="ERROR")[0]["category"], "ocr")

                clear_log_entries()
                self.assertEqual(get_log_entries(), [])
            finally:
                configure_logging(Path(tempfile.gettempdir()) / "subtitleyc-test-logs")
                clear_log_entries()

    def test_parse_srt_and_export_txt_and_ass(self):
        srt = (
            "1\n00:00:01,500 --> 00:00:03,000\nHello\nWorld\n\n"
            "2\n00:00:04,000 --> 00:00:05,250\nSecond line\n"
        )

        cues = parse_srt(srt)

        self.assertEqual(len(cues), 2)
        self.assertEqual(cues[0].text, "Hello\nWorld")
        self.assertEqual(cues_to_txt(cues), "Hello World\nSecond line\n")
        ass = cues_to_ass(cues, title="Demo")
        self.assertIn("[Script Info]", ass)
        self.assertIn("Dialogue: 0,0:00:01.50,0:00:03.00", ass)
        self.assertIn(r"Hello\NWorld", ass)
        parsed_ass = parse_ass(ass)
        self.assertEqual(parsed_ass[0].text, "Hello\nWorld")

if __name__ == "__main__":
    unittest.main()
