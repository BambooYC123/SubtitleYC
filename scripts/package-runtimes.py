"""Build pinned, independently downloadable OCR packages before compiling the app."""
import argparse
import hashlib
import json
import re
import zipfile
from pathlib import Path


def package(source: Path, edition: str, output: Path, release: str) -> dict:
    if not (source / "videocr-cli.exe").is_file():
        raise ValueError(f"Missing videocr-cli.exe in {source}")
    version = re.search(r"v(\d+\.\d+\.\d+)", source.name)
    if not version:
        raise ValueError("Runtime source folder must include its version")
    name = f"SubtitleYC-{release}-ocr-{edition}.zip"
    output.mkdir(parents=True, exist_ok=True)
    archive = output / name
    pending = output / (name + ".building")
    files = sorted(p for p in source.rglob("*") if p.is_file())
    total = sum(p.stat().st_size for p in files)
    print(f"Packaging {edition}: {total / 1024**3:.2f} GB", flush=True)
    # LZMA ZIP uses Python's built-in reader; no extra extractor is downloaded or executed.
    with zipfile.ZipFile(pending, "w", compression=zipfile.ZIP_LZMA, allowZip64=True) as zipped:
        for path in files:
            if path.is_symlink():
                raise ValueError(f"Runtime contains a symbolic link: {path}")
            zipped.write(path, (Path(source.name) / path.relative_to(source)).as_posix())
    if pending.stat().st_size >= 2 * 1024**3:
        raise ValueError(f"{name} exceeds the release asset size budget")
    pending.replace(archive)
    digest = hashlib.sha256()
    with archive.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    checksum = digest.hexdigest()
    archive.with_suffix(".zip.sha256").write_text(f"{checksum}  {name}\n", encoding="ascii")
    print(f"Ready: {archive} ({archive.stat().st_size / 1024**2:.1f} MB)", flush=True)
    return {"version": version[1], "url": f"https://github.com/BambooYC123/SubtitleYC/releases/download/v{release}/{name}",
            "sha256": checksum, "size_bytes": archive.stat().st_size, "unpacked_bytes": total,
            "cli": f"{source.name}/videocr-cli.exe"}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cpu", type=Path, required=True)
    parser.add_argument("--gpu", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--release", default="0.6.0")
    parser.add_argument("--catalog", type=Path, default=Path(__file__).resolve().parents[1] / "assets/runtime-catalog.json")
    args = parser.parse_args()
    catalog = {"cpu": package(args.cpu, "cpu", args.output, args.release),
               "gpu-cuda-12.9": package(args.gpu, "gpu-cuda-12.9", args.output, args.release)}
    if catalog["cpu"]["version"] != catalog["gpu-cuda-12.9"]["version"]:
        raise ValueError("CPU and GPU runtime versions must match")
    args.catalog.write_text(json.dumps(catalog, indent=2) + "\n", encoding="utf-8")
