from __future__ import annotations

import ipaddress
import socket
import threading
import urllib.parse
from contextlib import contextmanager
from typing import Any, Iterator


_DNS_GUARD_LOCK = threading.RLock()


def _is_public_address(value: str) -> bool:
    address = ipaddress.ip_address(value.split("%", 1)[0])
    if address.version == 6 and getattr(address, "ipv4_mapped", None) is not None:
        address = address.ipv4_mapped
    return bool(
        address.is_global
        and not address.is_loopback
        and not address.is_link_local
        and not address.is_multicast
        and not address.is_private
        and not address.is_reserved
        and not address.is_unspecified
    )


def _ensure_public_results(host: str, results: list[tuple[Any, ...]]) -> None:
    addresses = {
        str(result[4][0])
        for result in results
        if len(result) > 4 and isinstance(result[4], tuple) and result[4]
    }
    if not addresses:
        raise RuntimeError(f"Could not resolve the video URL host: {host}")
    try:
        unsafe = sorted(address for address in addresses if not _is_public_address(address))
    except ValueError as exc:
        raise RuntimeError(f"The video URL host returned an invalid network address: {host}") from exc
    if unsafe:
        raise RuntimeError("Video URLs must not point to this device or a private network address.")


def _resolve_public_host(host: str, port: int) -> None:
    clean_host = host.casefold().rstrip(".")
    if clean_host == "localhost" or clean_host.endswith(".localhost"):
        raise RuntimeError("Video URLs must not point to this device or a private network address.")
    try:
        results = socket.getaddrinfo(clean_host, port, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise RuntimeError(f"Could not resolve the video URL host: {host}") from exc
    _ensure_public_results(host, results)


def validate_public_http_url(value: str) -> str:
    url = str(value or "").strip()
    if len(url) > 8192:
        raise RuntimeError("The video URL is too long.")
    try:
        parsed = urllib.parse.urlsplit(url)
        port = parsed.port
    except ValueError as exc:
        raise RuntimeError("Enter a valid video URL.") from exc
    scheme = parsed.scheme.casefold()
    if scheme not in {"http", "https"} or not parsed.hostname:
        raise RuntimeError("Only http:// and https:// video URLs are supported.")
    if parsed.username is not None or parsed.password is not None:
        raise RuntimeError("Video URLs must not contain embedded usernames or passwords.")
    _resolve_public_host(parsed.hostname, port or (443 if scheme == "https" else 80))
    return url


@contextmanager
def public_network_only() -> Iterator[None]:
    """Reject non-public DNS results at the point a worker opens a connection."""

    with _DNS_GUARD_LOCK:
        original_getaddrinfo = socket.getaddrinfo

        def guarded_getaddrinfo(
            host: Any,
            port: Any,
            *args: Any,
            **kwargs: Any,
        ) -> list[tuple[Any, ...]]:
            results = original_getaddrinfo(host, port, *args, **kwargs)
            _ensure_public_results(str(host), results)
            return results

        socket.getaddrinfo = guarded_getaddrinfo
        try:
            yield
        finally:
            socket.getaddrinfo = original_getaddrinfo
