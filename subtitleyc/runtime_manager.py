"""Opt-in, pinned OCR downloads. Completed runtimes live outside the workspace cache."""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import stat
import sys
import threading
import time
import urllib.request
import zipfile
from pathlib import Path, PurePosixPath
from typing import Any

from . import __version__
from .gpu_compatibility import gpu_compatibility


def runtime_store() -> Path:
    if os.environ.get("SUBTITLEYC_RUNTIME_DIR"):
        return Path(os.environ["SUBTITLEYC_RUNTIME_DIR"])
    base = Path(os.environ.get("LOCALAPPDATA", str(Path.home() / ".local/share")))
    return base / "SubtitleYC" / "runtimes"


def load_catalog() -> dict[str, Any]:
    root = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
    path = root / "assets" / "runtime-catalog.json"
    if not path.is_file():
        return {}
    catalog = json.loads(path.read_text(encoding="utf-8-sig"))
    for edition, item in catalog.items():
        if edition not in {"cpu", "gpu-cuda-12.9"}:
            raise ValueError("Unknown OCR runtime edition")
        if not re.fullmatch(r"[0-9a-f]{64}", item["sha256"]):
            raise ValueError("Invalid OCR runtime checksum")
        if not item["url"].startswith("https://github.com/BambooYC123/SubtitleYC/releases/download/"):
            raise ValueError("Invalid OCR runtime download address")
        if item["size_bytes"] <= 0 or item["unpacked_bytes"] <= 0:
            raise ValueError("Invalid OCR runtime size")
        safe_member(item["cli"])
    return catalog


def safe_member(name: str) -> Path:
    parts = PurePosixPath(name).parts
    reserved = {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))}
    if (not parts or "\\" in name or name.startswith("/")
            or any(p in {".", ".."} or ":" in p or p.endswith((" ", "."))
                   or p.split(".")[0].upper() in reserved for p in parts)):
        raise ValueError("Unsafe file path in OCR runtime package")
    return Path(*parts)


class DownloadCancelled(Exception):
    pass


class RuntimeManager:
    def __init__(self, catalog: dict[str, Any], root: Path | None = None):
        self.catalog = catalog
        self.root = root if root is not None else runtime_store()
        self.app_root = (Path(sys.executable).resolve().parent if getattr(sys, "frozen", False)
                         else Path(__file__).resolve().parent.parent) if root is None else None
        self.lock = threading.RLock()
        self.cancel_event = threading.Event()
        self.worker: threading.Thread | None = None
        self.state: dict[str, Any] = {"status": "idle", "edition": None, "bytes": 0, "total": 0, "speed": 0, "error": None}

    def target(self, edition: str) -> Path:
        item = self.catalog[edition]
        # Keep nested PaddleOCR paths below legacy Windows path limits where possible.
        # The completion marker still checks the entire SHA-256, not just this prefix.
        return self.root / f"{edition}-{item['sha256'][:16]}"

    def installed_cli(self, edition: str) -> str | None:
        item = self.catalog.get(edition)
        if not item:
            return None
        if self.app_root:
            bundled = self.app_root / "tools" / "VideOCR" / safe_member(item["cli"])
            if bundled.is_file():
                return str(bundled)
        folder = self.target(edition)
        cli = folder / safe_member(item["cli"])
        try:
            if (folder / ".complete").read_text() == item["sha256"] and cli.is_file():
                return str(cli)
        except OSError:
            pass
        return None

    def snapshot(self) -> dict[str, Any]:
        with self.lock:
            app_bytes = 0
            if self.app_root:
                try:
                    app_bytes = json.loads((self.app_root / "_internal/assets/install-size.json").read_text())["app_size_bytes"]
                except (OSError, ValueError, KeyError):
                    pass
            editions = [
                {"id": key, "version": value["version"], "size_bytes": value["size_bytes"],
                 "unpacked_bytes": value["unpacked_bytes"], "installed": bool(self.installed_cli(key)),
                 "required_free_bytes": self.required_space(key),
                 "compatibility": gpu_compatibility() if key == "gpu-cuda-12.9" else {"compatible": True}}
                for key, value in self.catalog.items()
            ]
            return {**self.state, "active": bool(self.worker and self.worker.is_alive()), "editions": editions,
                    "app_version": __version__, "app_size_bytes": app_bytes,
                    "current_install_bytes": app_bytes + sum(e["unpacked_bytes"] for e in editions if e["installed"])}

    def required_space(self, edition: str) -> int:
        if self.installed_cli(edition):
            return 0
        item = self.catalog[edition]
        partial = self.root / f"{item['sha256']}.zip.part"
        try:
            existing = partial.stat().st_size
        except OSError:
            existing = 0
        if existing > item["size_bytes"]:
            existing = 0
        return max(0, item["size_bytes"] - existing) + item["unpacked_bytes"] + 256 * 1024**2

    def start(self, edition: str) -> dict[str, Any]:
        with self.lock:
            if edition not in self.catalog:
                raise ValueError("This OCR runtime is not available in this build.")
            if edition == "gpu-cuda-12.9":
                compatibility = gpu_compatibility(refresh=True)
                if not compatibility["compatible"]:
                    raise ValueError(compatibility["reason"])
            if self.worker and self.worker.is_alive():
                raise RuntimeError("An OCR runtime download is already running.")
            if self.installed_cli(edition):
                self.state.update(status="ready", edition=edition, error=None)
                return self.snapshot()
            self.cancel_event.clear()
            self.state = {"status": "downloading", "edition": edition, "bytes": 0,
                          "total": self.catalog[edition]["size_bytes"], "speed": 0, "error": None}
            self.worker = threading.Thread(target=self._run, args=(edition,), daemon=True)
            self.worker.start()
            return self.snapshot()

    def cancel(self) -> dict[str, Any]:
        self.cancel_event.set()
        return self.snapshot()

    def _check_cancel(self) -> None:
        if self.cancel_event.is_set():
            raise DownloadCancelled()

    def _update(self, **values: Any) -> None:
        with self.lock:
            self.state.update(values)

    def _download(self, item: dict[str, Any], partial: Path) -> None:
        offset = partial.stat().st_size if partial.exists() else 0
        if offset > item["size_bytes"]:
            partial.unlink()
            offset = 0
        if offset == item["size_bytes"]:
            return
        headers = {"User-Agent": "SubtitleYC-Runtime-Installer", "Accept-Encoding": "identity"}
        if offset:
            headers["Range"] = f"bytes={offset}-"
        with urllib.request.urlopen(urllib.request.Request(item["url"], headers=headers), timeout=30) as response:
            if response.status == 206:
                expected_range = f"bytes {offset}-{item['size_bytes'] - 1}/{item['size_bytes']}"
                if response.headers.get("Content-Range") != expected_range:
                    raise ValueError("Download server returned an unexpected byte range. Please retry.")
            elif response.status == 200:
                offset = 0  # Server does not support resume: safely restart.
            else:
                raise ValueError("Download server returned an unexpected response.")
            started = time.monotonic()
            received = 0
            with partial.open("ab" if offset else "wb") as output:
                while True:
                    self._check_cancel()
                    chunk = response.read(1024 * 1024)
                    if not chunk:
                        break
                    if offset + received + len(chunk) > item["size_bytes"]:
                        raise ValueError("Download exceeds the expected package size.")
                    output.write(chunk)
                    received += len(chunk)
                    self._update(bytes=offset + received, speed=received / max(time.monotonic() - started, 0.01))
            if offset + received != item["size_bytes"]:
                raise ValueError("Download was interrupted. Choose Download / Resume to continue.")

    def _extract(self, item: dict[str, Any], archive_path: Path, staging: Path) -> None:
        with zipfile.ZipFile(archive_path) as archive:
            entries = archive.infolist()
            if len(entries) > 100000 or sum(e.file_size for e in entries) != item["unpacked_bytes"]:
                raise ValueError("OCR package contents do not match the expected size.")
            seen = set()
            for entry in entries:
                relative = safe_member(entry.filename)
                key = str(relative).casefold()
                if key in seen or stat.S_ISLNK(entry.external_attr >> 16):
                    raise ValueError("Duplicate file or link in OCR runtime package.")
                seen.add(key)
                destination = staging / relative
                if entry.is_dir():
                    destination.mkdir(parents=True, exist_ok=True)
                    continue
                destination.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(entry) as source, destination.open("wb") as output:
                    while True:
                        self._check_cancel()
                        chunk = source.read(1024 * 1024)
                        if not chunk:
                            break
                        output.write(chunk)
        if not (staging / safe_member(item["cli"])).is_file():
            raise ValueError("The OCR executable is missing from this package.")

    def _run(self, edition: str) -> None:
        # Multiple desktop processes can share the store. The OS releases this lock on exit.
        try:
            self.root.mkdir(parents=True, exist_ok=True)
            with (self.root / ".download.lock").open("a+b") as lock_file:
                if lock_file.tell() == 0:
                    lock_file.write(b"0")
                    lock_file.flush()
                lock_file.seek(0)
                try:
                    if os.name == "nt":
                        import msvcrt
                        msvcrt.locking(lock_file.fileno(), msvcrt.LK_NBLCK, 1)
                    else:
                        import fcntl
                        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                except OSError as exc:
                    raise RuntimeError("Another SubtitleYC window is downloading a runtime. Retry after it finishes.") from exc
                try:
                    self._install(edition)
                finally:
                    lock_file.seek(0)
                    if os.name == "nt":
                        msvcrt.locking(lock_file.fileno(), msvcrt.LK_UNLCK, 1)
                    else:
                        fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
        except Exception as exc:  # noqa: BLE001 - background failures must reach the UI.
            self._update(status="error", speed=0, error=str(exc))

    def _install(self, edition: str) -> None:
        item = self.catalog[edition]
        partial = self.root / f"{item['sha256']}.zip.part"
        staging = self.root / f"{edition}.extracting"
        try:
            self.root.mkdir(parents=True, exist_ok=True)
            if self.installed_cli(edition):
                self._update(status="ready", error=None)
                return
            if staging.exists():
                shutil.rmtree(staging)
            target = self.target(edition)
            if target.exists():
                # Not a usable install (checked above), e.g. antivirus removed a file.
                # Clear it now rather than failing after the whole download.
                shutil.rmtree(target)
            required = self.required_space(edition)
            if shutil.disk_usage(self.root).free < required:
                raise ValueError(f"Not enough disk space. Free at least {required / 1024**3:.1f} GB and retry.")
            self._download(item, partial)
            self._update(status="verifying", bytes=item["size_bytes"], speed=0)
            digest = hashlib.sha256()
            with partial.open("rb") as source:
                while chunk := source.read(1024 * 1024):
                    self._check_cancel()
                    digest.update(chunk)
            if digest.hexdigest() != item["sha256"]:
                partial.unlink()
                raise ValueError("Download verification failed. Please download the runtime again.")
            self._update(status="installing")
            staging.mkdir()
            self._extract(item, partial, staging)
            self._check_cancel()
            (staging / ".complete").write_text(item["sha256"])
            staging.rename(target)
            partial.unlink(missing_ok=True)
            self._update(status="ready", error=None)
        except DownloadCancelled:
            self._update(status="paused", speed=0, error=None)
        except Exception as exc:  # noqa: BLE001 - download/archive failures must reach the UI.
            self._update(status="error", speed=0, error=str(exc))
        finally:
            if staging.exists():
                shutil.rmtree(staging, ignore_errors=True)


manager = RuntimeManager(load_catalog())
