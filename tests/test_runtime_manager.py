import hashlib
import io
import zipfile
from pathlib import Path

import pytest

from subtitleyc.runtime_manager import RuntimeManager, safe_member


def fixture_package(tmp_path, names=None):
    data = io.BytesIO()
    entries = names or {"videocr-cli-CPU-v1.5.1/videocr-cli.exe": b"fixture executable", "models/test.bin": b"model"}
    with zipfile.ZipFile(data, "w", zipfile.ZIP_LZMA) as archive:
        for name, value in entries.items():
            archive.writestr(name, value)
    raw = data.getvalue()
    item = {"version": "1.5.1", "url": "https://github.com/BambooYC123/SubtitleYC/releases/download/v0.6.0/test.zip",
            "sha256": hashlib.sha256(raw).hexdigest(), "size_bytes": len(raw),
            "unpacked_bytes": sum(map(len, entries.values())), "cli": "videocr-cli-CPU-v1.5.1/videocr-cli.exe"}
    manager = RuntimeManager({"cpu": item}, tmp_path / "runtimes")
    return manager, item, raw


class Response(io.BytesIO):
    def __init__(self, content, status=200, headers=None):
        super().__init__(content)
        self.status = status
        self.headers = headers or {}


def run_download(manager):
    manager.start("cpu")
    manager.worker.join(5)
    assert not manager.worker.is_alive()
    return manager.snapshot()


def test_install_is_verified_and_reused_after_app_restart(tmp_path, monkeypatch):
    manager, _item, raw = fixture_package(tmp_path)
    monkeypatch.setattr("urllib.request.urlopen", lambda *a, **kw: Response(raw))
    assert run_download(manager)["status"] == "ready"
    assert Path(manager.installed_cli("cpu")).read_bytes() == b"fixture executable"
    restarted = RuntimeManager(manager.catalog, manager.root)
    monkeypatch.setattr("urllib.request.urlopen", lambda *a, **kw: pytest.fail("Installed runtimes must not download again"))
    assert restarted.start("cpu")["status"] == "ready"


def test_interrupted_download_resumes_exact_range(tmp_path, monkeypatch):
    manager, _item, raw = fixture_package(tmp_path)
    monkeypatch.setattr("urllib.request.urlopen", lambda *a, **kw: Response(raw[:50]))
    assert run_download(manager)["status"] == "error"
    assert manager.installed_cli("cpu") is None

    def resumed(request, **kwargs):
        assert request.get_header("Range") == "bytes=50-"
        return Response(raw[50:], 206, {"Content-Range": f"bytes 50-{len(raw)-1}/{len(raw)}"})

    monkeypatch.setattr("urllib.request.urlopen", resumed)
    assert run_download(manager)["status"] == "ready"


def test_server_ignoring_range_restarts_safely(tmp_path, monkeypatch):
    manager, item, raw = fixture_package(tmp_path)
    manager.root.mkdir()
    (manager.root / f"{item['sha256']}.zip.part").write_bytes(raw[:50])
    monkeypatch.setattr("urllib.request.urlopen", lambda *a, **kw: Response(raw))
    assert run_download(manager)["status"] == "ready"


def test_hash_failure_never_activates_runtime(tmp_path, monkeypatch):
    manager, _item, raw = fixture_package(tmp_path)
    monkeypatch.setattr("urllib.request.urlopen", lambda *a, **kw: Response(b"x" * len(raw)))
    result = run_download(manager)
    assert result["status"] == "error"
    assert "verification failed" in result["error"]
    assert manager.installed_cli("cpu") is None
    assert not list(manager.root.glob("*.part"))


@pytest.mark.parametrize("path", ["../escape.exe", "/absolute.exe", "C:/escape.exe", "folder\\escape.exe", "NUL.txt", "folder/file:stream", "folder./file"])
def test_reject_unsafe_windows_archive_paths(path):
    with pytest.raises(ValueError):
        safe_member(path)


def test_unsafe_zip_does_not_escape_or_activate(tmp_path, monkeypatch):
    manager, _item, raw = fixture_package(tmp_path, {"../../escape.exe": b"bad"})
    monkeypatch.setattr("urllib.request.urlopen", lambda *a, **kw: Response(raw))
    assert run_download(manager)["status"] == "error"
    assert not (tmp_path / "escape.exe").exists()
    assert manager.installed_cli("cpu") is None


def test_not_enough_disk_does_not_download(tmp_path, monkeypatch):
    manager, _item, _raw = fixture_package(tmp_path)
    from types import SimpleNamespace
    monkeypatch.setattr("shutil.disk_usage", lambda p: SimpleNamespace(free=1))
    monkeypatch.setattr("urllib.request.urlopen", lambda *a, **kw: pytest.fail("Should check disk space first"))
    assert "Not enough disk space" in run_download(manager)["error"]


def test_pause_leaves_partial_for_resume(tmp_path, monkeypatch):
    manager, item, raw = fixture_package(tmp_path)

    class PausingResponse(Response):
        def read(self, size=-1):
            chunk = super().read(50)
            manager.cancel()
            return chunk

    monkeypatch.setattr("urllib.request.urlopen", lambda *a, **kw: PausingResponse(raw))
    assert run_download(manager)["status"] == "paused"
    assert manager.installed_cli("cpu") is None
    assert (manager.root / f"{item['sha256']}.zip.part").stat().st_size == 50


def test_runtime_endpoints_require_authentication_and_reject_unknown_edition():
    from fastapi.testclient import TestClient

    from subtitleyc.main import API_TOKEN, app
    client = TestClient(app)
    assert client.post("/api/runtimes/cpu/download").status_code == 401
    response = client.post("/api/runtimes/unknown/download", headers={"X-SubtitleYC-Token": API_TOKEN})
    assert response.status_code == 400


def test_welcome_dismissal_persists(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from subtitleyc import main

    monkeypatch.setattr(main, "DATA_DIR", tmp_path)
    client = TestClient(main.app)
    headers = {"X-SubtitleYC-Token": main.API_TOKEN}
    assert client.post("/api/onboarding/complete").status_code == 401
    assert client.get("/api/onboarding", headers=headers).json()["show_welcome"]
    assert client.post("/api/onboarding/complete", headers=headers).status_code == 200
    reopened = TestClient(main.app)
    assert not reopened.get("/api/onboarding", headers=headers).json()["show_welcome"]


def test_native_preview_modal_updates_never_show_video():
    from types import SimpleNamespace
    from unittest.mock import Mock

    from subtitleyc.qt_desktop import NativePreviewSurface

    surface = SimpleNamespace(hide=Mock(), set_session=Mock())
    for _ in range(3):
        NativePreviewSurface.configure(surface, {"visible": False}, {"session_id": "playing"})
    assert surface.hide.call_count == 3
    surface.set_session.assert_not_called()


def test_installer_cpu_is_detected_and_included_in_size(tmp_path):
    manager, item, _ = fixture_package(tmp_path)
    manager.app_root = tmp_path / "app"
    cli = manager.app_root / "tools/VideOCR" / item["cli"]
    cli.parent.mkdir(parents=True)
    cli.write_bytes(b"installed by setup")
    metadata = manager.app_root / "_internal/assets/install-size.json"
    metadata.parent.mkdir(parents=True)
    metadata.write_text('{"app_size_bytes": 1234}')
    snapshot = manager.snapshot()
    assert snapshot["editions"][0]["installed"]
    assert snapshot["editions"][0]["required_free_bytes"] == 0
    assert snapshot["current_install_bytes"] == 1234 + item["unpacked_bytes"]
    assert snapshot["app_version"] == "0.7.0"
    assert manager.start("cpu")["status"] == "ready"
    assert manager.worker is None


def test_space_estimate_matches_resumable_download(tmp_path):
    manager, item, _ = fixture_package(tmp_path)
    complete_required = item["size_bytes"] + item["unpacked_bytes"] + 256 * 1024**2
    assert manager.required_space("cpu") == complete_required
    manager.root.mkdir(parents=True, exist_ok=True)
    partial = manager.root / f"{item['sha256']}.zip.part"
    partial.write_bytes(b"0" * 10)
    assert manager.required_space("cpu") == complete_required - 10
