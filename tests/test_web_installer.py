import hashlib
import importlib.util
import json
import zipfile
from pathlib import Path


def test_web_payload_and_embedded_pins_match(tmp_path):
    root = Path(__file__).resolve().parents[1]
    spec = importlib.util.spec_from_file_location("web_package", root / "scripts/package-web-installer.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    dist = tmp_path / "dist"
    (dist / "_internal/assets").mkdir(parents=True)
    (dist / "SubtitleYC.exe").write_bytes(b"fixture executable")
    catalog = tmp_path / "catalog.json"
    catalog.write_text(json.dumps({"cpu": {
        "url": "https://github.com/BambooYC123/SubtitleYC/releases/download/v0.6.0/cpu.zip",
        "sha256": "a" * 64, "unpacked_bytes": 456, "size_bytes": 123,
    }}))
    output = tmp_path / "release"
    module.package(dist, output, "0.6.0", catalog)
    pins = json.loads((output / "WEB-INSTALLER-PAYLOAD.json").read_text())
    archive = output / pins["WebAppFile"]
    assert hashlib.sha256(archive.read_bytes()).hexdigest() == pins["WebAppHash"]
    with zipfile.ZipFile(archive) as zf:
        assert sum(item.file_size for item in zf.infolist()) == pins["WebAppInstalled"]
        assert zf.read("SubtitleYC.exe") == b"fixture executable"
    assert pins["WebDownloadBytes"] == archive.stat().st_size + 123
    assert pins["WebCpuInstalled"] == 456
