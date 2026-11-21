"""Package the app separately from the small, hash-pinned Windows web installer."""
import argparse
import hashlib
import json
import zipfile
from pathlib import Path


def package(dist: Path, output: Path, version: str, catalog: Path) -> None:
    output.mkdir(parents=True, exist_ok=True)
    editions = json.loads(catalog.read_text(encoding="utf-8-sig"))
    cpu = editions["cpu"]
    gpu = editions.get("gpu-cuda-12.9")
    if not cpu["url"].startswith(f"https://github.com/BambooYC123/SubtitleYC/releases/download/v{version}/"):
        raise ValueError("CPU payload URL must match the web installer's version")
    if not (dist / "SubtitleYC.exe").is_file():
        raise ValueError("Build the core application first")
    if list((dist / "tools").rglob("videocr-cli.exe")):
        raise ValueError("App payload must be a core build; CPU is a separate verified payload")
    metadata = dist / "_internal/assets/install-size.json"
    files = sorted(p for p in dist.rglob("*") if p.is_file() and p != metadata)
    app_bytes = sum(p.stat().st_size for p in files)
    value = {"app_version": version, "app_size_bytes": app_bytes}
    for _ in range(5):
        raw = json.dumps(value, indent=2).encode()
        value["app_size_bytes"] = app_bytes + len(raw)
    metadata.write_bytes(json.dumps(value, indent=2).encode())
    files.append(metadata)
    archive = output / f"SubtitleYC-{version}-windows-app.zip"
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED, compresslevel=6, allowZip64=True) as zf:
        for path in files:
            zf.write(path, path.relative_to(dist).as_posix())
    with archive.open("rb") as source:
        digest = hashlib.file_digest(source, "sha256").hexdigest()
    archive.with_suffix(".zip.sha256").write_text(f"{digest}  {archive.name}\n", encoding="ascii")
    definitions = {
        "WebAppFile": archive.name,
        "WebAppUrl": f"https://github.com/BambooYC123/SubtitleYC/releases/download/v{version}/{archive.name}",
        "WebAppHash": digest, "WebAppInstalled": value["app_size_bytes"],
        "WebCpuFile": cpu["url"].rsplit("/", 1)[1], "WebCpuUrl": cpu["url"],
        "WebCpuHash": cpu["sha256"], "WebCpuInstalled": cpu["unpacked_bytes"],
        "WebDownloadBytes": archive.stat().st_size + cpu["size_bytes"],
        "WebDownloadMiB": f'{(archive.stat().st_size + cpu["size_bytes"]) / 1024**2:.0f}',
        "WebInstalledGiB": f'{(value["app_size_bytes"] + cpu["unpacked_bytes"]) / 1024**3:.2f}',
    }
    if gpu:
        # Shown on setup's OCR engines page; the app does the download itself on first launch.
        definitions["GpuDownloadGiB"] = f'{gpu["size_bytes"] / 1024**3:.2f}'
        definitions["GpuInstalledGiB"] = f'{gpu["unpacked_bytes"] / 1024**3:.2f}'
    (output / "web-payload.iss").write_text("\n".join(
        f'#define {key} {json.dumps(value)}' for key, value in definitions.items()
    ), encoding="utf-8")
    (output / "WEB-INSTALLER-PAYLOAD.json").write_text(json.dumps(definitions, indent=2), encoding="utf-8")
    print(json.dumps(definitions, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dist", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--version", required=True)
    parser.add_argument("--catalog", type=Path, default=Path("assets/runtime-catalog.json"))
    args = parser.parse_args()
    package(args.dist, args.output, args.version, args.catalog)
