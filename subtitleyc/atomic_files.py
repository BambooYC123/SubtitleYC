"""Replace saved text only after a complete, flushed write; retain one backup."""

import os
import tempfile
import threading
from pathlib import Path


_write_lock = threading.RLock()


def _replace_bytes(path: Path, content: bytes) -> None:
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def save_text(path: Path, content: str) -> None:
    """Keep the prior successful save in <filename>.bak, failing safely on I/O errors."""
    with _write_lock:
        if path.exists():
            _replace_bytes(path.with_name(path.name + ".bak"), path.read_bytes())
        _replace_bytes(path, content.encode("utf-8"))
