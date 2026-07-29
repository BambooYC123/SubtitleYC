import shutil
import socket
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from subtitleyc.main import (
    API_TOKEN,
    MIN_FREE_DISK_BYTES,
    _ensure_free_disk,
    _validate_remote_url,
    app,
)
from subtitleyc.logs import (
    clear_log_entries,
    get_log_entries,
    log_event,
    record_crash,
    redact_sensitive_text,
)
from subtitleyc.security import public_network_only


def _dns_result(address: str, port: int = 443):
    family = socket.AF_INET6 if ":" in address else socket.AF_INET
    sockaddr = (address, port, 0, 0) if family == socket.AF_INET6 else (address, port)
    return [(family, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", sockaddr)]


class TestLocalAppSecurity(unittest.TestCase):
    def test_api_requires_session_authentication(self):
        response = TestClient(app).get("/api/settings")
        self.assertEqual(response.status_code, 401)

    def test_authenticated_api_request_is_allowed(self):
        client = TestClient(app, headers={"X-SubtitleYC-Token": API_TOKEN})
        self.assertEqual(client.get("/api/settings").status_code, 200)

    def test_foreign_host_is_rejected(self):
        client = TestClient(
            app,
            base_url="http://attacker.example",
            headers={"X-SubtitleYC-Token": API_TOKEN},
        )
        self.assertEqual(client.get("/api/settings").status_code, 400)

    def test_foreign_origin_cannot_change_settings(self):
        client = TestClient(app, headers={"X-SubtitleYC-Token": API_TOKEN})
        response = client.put(
            "/api/settings",
            headers={"Origin": "https://attacker.example"},
            json={},
        )
        self.assertEqual(response.status_code, 403)

    def test_launch_token_becomes_http_only_session_cookie(self):
        client = TestClient(app, follow_redirects=False)
        response = client.get(f"/?app_token={API_TOKEN}")
        self.assertEqual(response.status_code, 303)
        cookie = response.headers.get("set-cookie", "").casefold()
        self.assertIn("httponly", cookie)
        self.assertIn("samesite=strict", cookie)
        self.assertEqual(client.get("/").status_code, 200)

    def test_video_upload_limit_removes_oversized_copy(self):
        client = TestClient(app, headers={"X-SubtitleYC-Token": API_TOKEN})
        with patch("subtitleyc.main.MAX_VIDEO_UPLOAD_BYTES", 4), patch(
            "subtitleyc.main.MAX_VIDEO_UPLOAD_MB", 1
        ):
            response = client.post(
                "/api/videos/upload",
                files={"file": ("oversized.mp4", b"12345", "video/mp4")},
            )
        self.assertEqual(response.status_code, 413)

    def test_video_upload_rejects_disguised_file_types(self):
        client = TestClient(app, headers={"X-SubtitleYC-Token": API_TOKEN})
        response = client.post(
            "/api/videos/upload",
            files={"file": ("not-a-video.exe", b"data", "application/octet-stream")},
        )
        self.assertEqual(response.status_code, 400)

    def test_remote_video_url_rejects_local_and_credentialed_urls(self):
        with self.assertRaises(RuntimeError):
            _validate_remote_url("file:///C:/private/video.mp4")
        with self.assertRaises(RuntimeError):
            _validate_remote_url("https://user:secret@example.com/video")
        with self.assertRaisesRegex(RuntimeError, "private network"):
            _validate_remote_url("http://127.0.0.1:8080/private")
        with self.assertRaisesRegex(RuntimeError, "private network"):
            _validate_remote_url("http://[::1]/private")

    def test_remote_video_url_checks_resolved_addresses(self):
        with patch("subtitleyc.security.socket.getaddrinfo", return_value=_dns_result("93.184.216.34")):
            self.assertEqual(
                _validate_remote_url("https://example.com/video"),
                "https://example.com/video",
            )

        with patch("subtitleyc.security.socket.getaddrinfo", return_value=_dns_result("192.168.1.20")):
            with self.assertRaisesRegex(RuntimeError, "private network"):
                _validate_remote_url("https://internal.example/video")

        mixed = [*_dns_result("93.184.216.34"), *_dns_result("10.0.0.8")]
        with patch("subtitleyc.security.socket.getaddrinfo", return_value=mixed):
            with self.assertRaisesRegex(RuntimeError, "private network"):
                _validate_remote_url("https://mixed.example/video")

    def test_worker_dns_guard_checks_connection_time_resolution(self):
        with patch("subtitleyc.security.socket.getaddrinfo", return_value=_dns_result("169.254.169.254")):
            with public_network_only(), self.assertRaisesRegex(RuntimeError, "private network"):
                socket.getaddrinfo("redirected.example", 443, type=socket.SOCK_STREAM)

    def test_logs_redact_urls_paths_and_tokens(self):
        message = (
            "source=C:\\Private Work\\secret video.mp4 token=secret-value "
            "url=https://user:pass@example.com/watch?v=private#cue"
        )
        redacted = redact_sensitive_text(message)
        self.assertNotIn("Private Work", redacted)
        self.assertNotIn("secret-value", redacted)
        self.assertNotIn("user:pass", redacted)
        self.assertNotIn("v=private", redacted)
        self.assertIn("source=<LOCAL_PATH>", redacted)
        self.assertIn("token=<REDACTED>", redacted)
        self.assertEqual(
            redact_sensitive_text("Downloaded video to D:\\Private Library\\private title.mp4"),
            "Downloaded video to <LOCAL_PATH>",
        )

        clear_log_entries()
        log_event(message, category="security-test")
        entries = get_log_entries(category="security-test")
        self.assertEqual(len(entries), 1)
        self.assertNotIn("secret-value", entries[0]["message"])

    def test_crash_logs_are_redacted_before_writing(self):
        with tempfile.TemporaryDirectory() as directory, patch(
            "subtitleyc.logs._crash_log_dir", Path(directory)
        ):
            path = record_crash(
                "Redaction test",
                traceback_text='File "C:\\Users\\alice\\Private\\worker.py", line 4',
                extra={"url": "https://example.com/watch?token=private", "token": "private-secret"},
            )
            self.assertIsNotNone(path)
            content = path.read_text(encoding="utf-8")
            self.assertNotIn("alice", content)
            self.assertNotIn("private-secret", content)
            self.assertNotIn("token=private", content)
            self.assertIn("<REDACTED", content)

    def test_disk_guard_reserves_minimum_free_space(self):
        usage = shutil._ntuple_diskusage(100, 99, MIN_FREE_DISK_BYTES - 1)
        with tempfile.TemporaryDirectory() as directory:
            with patch("subtitleyc.main.shutil.disk_usage", return_value=usage):
                with self.assertRaises(RuntimeError):
                    _ensure_free_disk(Path(directory))


if __name__ == "__main__":
    unittest.main()
