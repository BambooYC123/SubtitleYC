"""Local preflight for the pinned VideOCR CUDA 12.9 Windows package."""
from __future__ import annotations

import csv
import io
import os
import re
import subprocess
import threading
import time
from pathlib import Path
from typing import Any

# Conservative full CUDA 12.9 Update 1 support, not CUDA minor-version compatibility.
# https://docs.nvidia.com/cuda/archive/12.9.1/cuda-toolkit-release-notes/index.html
MIN_DRIVER = (576, 57)
_lock = threading.Lock()
_cached: dict[str, Any] | None = None
_expires = 0.0


def evaluate_gpus(output: str) -> dict[str, Any]:
    devices = []
    for row in csv.reader(io.StringIO(output)):
        if len(row) != 2:
            continue
        name, driver = (value.strip() for value in row)
        supported = bool(re.search(r"\bGeForce\s+(?:GTX\s*16\d{2}|RTX\s*[2345]0\d{2})\b", name, re.IGNORECASE))
        version = re.fullmatch(r"(\d+)\.(\d+)", driver)
        devices.append({"name": name, "driver": driver})
        if supported and version and tuple(map(int, version.groups())) >= MIN_DRIVER:
            return {"compatible": True, "reason": "GPU and driver checks passed.", "devices": devices}
    supported_devices = [d for d in devices if re.search(r"\bGeForce\s+(?:GTX\s*16\d{2}|RTX\s*[2345]0\d{2})\b", d["name"], re.IGNORECASE)]
    if supported_devices:
        reason = "Update the Nvidia driver to 576.57 or newer, then check again. CPU OCR is available now."
    elif devices:
        reason = "This GPU is not verified for this package. It supports GeForce GTX 16 and RTX 20–50 series. Use CPU OCR."
    else:
        reason = "No Nvidia GPU was reported by the driver. Use CPU OCR."
    return {"compatible": False, "reason": reason, "devices": devices}


def gpu_compatibility(*, refresh: bool = False) -> dict[str, Any]:
    global _cached, _expires
    with _lock:
        if not refresh and _cached is not None and time.monotonic() < _expires:
            return _cached
        candidates = [
            Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32/nvidia-smi.exe",
            Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "NVIDIA Corporation/NVSMI/nvidia-smi.exe",
        ]
        executable = next((path for path in candidates if path.is_file()), None)
        result: dict[str, Any] = {
            "compatible": False,
            "reason": "Could not verify an Nvidia GPU and driver. Install or update the Nvidia driver, then check again, or use CPU OCR.",
            "devices": [],
        }
        if executable:
            try:
                process = subprocess.run(
                    [str(executable), "--query-gpu=name,driver_version", "--format=csv,noheader,nounits"],
                    capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=5,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0), check=False,
                )
                if process.returncode == 0:
                    result = evaluate_gpus(process.stdout)
            except (OSError, subprocess.TimeoutExpired):
                pass
        _cached, _expires = result, time.monotonic() + 30
        return result
