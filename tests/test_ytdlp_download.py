import json
import os
import subprocess
import sys
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from subtitleyc import ytdlp_download


_SUCCESS_WORKER = """
import json
import sys
from pathlib import Path

result_path = Path(sys.argv[1])
progress_path = Path(sys.argv[2])
progress_path.write_text(
    json.dumps(
        {
            "status": "downloading",
            "downloaded_bytes": 50,
            "total_bytes": 100,
            "speed": 1024,
        }
    ),
    encoding="utf-8",
)
result_path.write_text(
    json.dumps(
        {
            "ok": True,
            "result": {
                "title": "Example",
                "filepath": "C:/video.mp4",
                "messages": [],
            },
        }
    ),
    encoding="utf-8",
)
"""


class TestYtDlpDownloadWorker(unittest.TestCase):
    def test_parent_reads_worker_result_and_progress(self):
        events = []

        def command(_request_path: Path, result_path: Path, progress_path: Path):
            return [sys.executable, "-c", _SUCCESS_WORKER, str(result_path), str(progress_path)]

        with patch.object(ytdlp_download, "_worker_command", command):
            result = ytdlp_download.download_in_subprocess(
                "https://example.com/video",
                {"quiet": True},
                progress=events.append,
            )

        self.assertEqual(result["title"], "Example")
        self.assertEqual(result["filepath"], "C:/video.mp4")
        self.assertTrue(events)
        self.assertEqual(events[-1]["downloaded_bytes"], 50)

    def test_unexpected_worker_exit_is_reported_without_exiting_parent(self):
        def command(_request_path: Path, _result_path: Path, _progress_path: Path):
            return [sys.executable, "-c", "import os; os._exit(23)"]

        with patch.object(ytdlp_download, "_worker_command", command):
            with self.assertRaisesRegex(RuntimeError, "engine crashed"):
                ytdlp_download.download_in_subprocess(
                    "https://example.com/video",
                    {"quiet": True},
                )

    def test_cancellation_terminates_worker(self):
        cancel_event = threading.Event()
        processes: list[subprocess.Popen] = []

        def command(_request_path: Path, _result_path: Path, _progress_path: Path):
            return [sys.executable, "-c", "import time; time.sleep(30)"]

        timer = threading.Timer(0.2, cancel_event.set)
        timer.start()
        started_at = time.monotonic()
        try:
            with patch.object(ytdlp_download, "_worker_command", command):
                with self.assertRaises(ytdlp_download.YtDlpDownloadCancelled):
                    ytdlp_download.download_in_subprocess(
                        "https://example.com/video",
                        {"quiet": True},
                        cancel_event=cancel_event,
                        process_callback=processes.append,
                    )
        finally:
            timer.cancel()

        self.assertLess(time.monotonic() - started_at, 5)
        self.assertEqual(len(processes), 1)
        self.assertIsNotNone(processes[0].poll())


if __name__ == "__main__":
    unittest.main()
