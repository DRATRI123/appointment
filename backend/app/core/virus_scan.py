"""Optional virus scanning of uploads with ClamAV (clamd's INSTREAM protocol over TCP).

Off by default (UPLOAD_SCANNER=none): uploads are already limited to a few file types that are checked by their
content, not their name, and stored encrypted outside the web folder. With UPLOAD_SCANNER=clamav every upload is sent
to clamd first (CLAMAV_HOST / CLAMAV_PORT; compose.production.yaml has an optional "antivirus" profile).
It fails closed: if the scanner cannot be reached, the upload is refused rather than accepted unscanned.
"""
from __future__ import annotations

import socket
import struct

from app.core.config import get_settings
from app.core.exceptions import ServiceUnavailable, ValidationFailed

CHUNK = 64 * 1024


def scan_bytes(data: bytes, *, host: str, port: int, timeout: float = 15.0) -> str | None:
    """Returns the virus name, or None when clean. Raises OSError when clamd cannot be reached."""
    with socket.create_connection((host, port), timeout=timeout) as sock:
        sock.sendall(b"zINSTREAM\0")
        for i in range(0, len(data), CHUNK):
            part = data[i:i + CHUNK]
            sock.sendall(struct.pack("!L", len(part)) + part)
        sock.sendall(struct.pack("!L", 0))
        reply = b""
        while not reply.endswith(b"\0"):
            got = sock.recv(4096)
            if not got:
                break
            reply += got
    text = reply.rstrip(b"\0").decode("utf-8", "replace")
    if text.endswith("OK"):
        return None
    if text.endswith("FOUND"):
        return text.split(":", 1)[-1].replace("FOUND", "").strip() or "unknown"
    raise OSError(f"Unexpected scanner reply: {text[:80]}")


def scan_upload(data: bytes) -> None:
    s = get_settings()
    if s.upload_scanner != "clamav":
        return
    try:
        found = scan_bytes(data, host=s.clamav_host, port=s.clamav_port)
    except OSError as exc:
        from app.core.logging import get_logger

        get_logger("upload").error("upload.scanner_unavailable", error=type(exc).__name__)
        raise ServiceUnavailable("Files cannot be checked for viruses right now. Please try again in a few minutes.", code="scanner_unavailable") from exc
    if found:
        from app.core.observability import security_event

        security_event("upload_infected")
        raise ValidationFailed("This file was refused because it contains malware.", code="file_infected")
