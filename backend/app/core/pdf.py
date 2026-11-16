"""A small text-only PDF writer (no extra dependency) for controlled exports: every page carries a diagonal
watermark and a confidentiality footer, so a printed or forwarded copy still says who exported it and when.

Uses the standard Helvetica font (Latin-1). Characters outside Latin-1 (for example Devanagari names) are replaced
with "?" in the PDF; the on-screen record is unaffected. A4 portrait.
"""
from __future__ import annotations

import textwrap
import zlib

PAGE_W, PAGE_H = 595, 842
MARGIN = 50
LINE = 14
WRAP = 95


def _esc(text: str) -> str:
    return text.encode("latin-1", "replace").decode("latin-1").replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def _wrap(lines: list[tuple[str, str]]) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    for style, text in lines:
        for part in (textwrap.wrap(text, WRAP) or [""]):
            out.append((style, part))
    return out


def build_pdf(*, title: str, lines: list[tuple[str, str]], watermark: str, footer: str) -> bytes:
    """``lines``: (style, text) with style "h" (heading), "b" (bold) or "" (normal)."""
    rows = _wrap(lines)
    per_page = (PAGE_H - 2 * MARGIN - 40) // LINE
    pages = [rows[i:i + per_page] for i in range(0, len(rows), per_page)] or [[]]
    objects: list[bytes] = []

    def add(obj: bytes) -> int:
        objects.append(obj)
        return len(objects)

    font = add(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>")
    bold = add(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold /Encoding /WinAnsiEncoding >>")
    faint = add(b"<< /Type /ExtGState /ca 0.10 /CA 0.10 >>")
    pages_id = len(objects) + 2 * len(pages) + 1  # the Pages object comes right after every page
    page_ids = []
    for n, page in enumerate(pages, 1):
        ops = [f"BT /F2 15 Tf {MARGIN} {PAGE_H - MARGIN} Td ({_esc(title)}) Tj ET"]
        y = PAGE_H - MARGIN - 30
        for style, text in page:
            f, size = ("/F2", 12) if style == "h" else ("/F2", 10) if style == "b" else ("/F1", 10)
            ops.append(f"BT {f} {size} Tf {MARGIN} {y} Td ({_esc(text)}) Tj ET")
            y -= LINE + (4 if style == "h" else 0)
        ops.append(f"BT /F1 8 Tf {MARGIN} 28 Td ({_esc(f'{footer}   Page {n} of {len(pages)}')}) Tj ET")
        # Diagonal watermark, repeated, faint: stays on screenshots and printouts of the PDF.
        ops.append("q /GS1 gs 0.4 g")
        for row in range(5):
            for col in range(2):
                ops.append(f"BT /F2 16 Tf 0.7071 0.7071 -0.7071 0.7071 {60 + col * 270} {80 + row * 160} Tm ({_esc(watermark)}) Tj ET")
        ops.append("Q")
        stream = zlib.compress("\n".join(ops).encode("latin-1"))
        content = add(b"<< /Length %d /Filter /FlateDecode >>\nstream\n" % len(stream) + stream + b"\nendstream")
        page_ids.append(add((f"<< /Type /Page /Parent {pages_id} 0 R /MediaBox [0 0 {PAGE_W} {PAGE_H}] /Contents {content} 0 R "
                             f"/Resources << /Font << /F1 {font} 0 R /F2 {bold} 0 R >> /ExtGState << /GS1 {faint} 0 R >> >> >>").encode()))
    kids = " ".join(f"{p} 0 R" for p in page_ids)
    if add(f"<< /Type /Pages /Kids [{kids}] /Count {len(page_ids)} >>".encode()) != pages_id:
        raise RuntimeError("PDF object numbering is inconsistent")
    catalog = add(f"<< /Type /Catalog /Pages {pages_id} 0 R >>".encode())
    info = add(f"<< /Title ({_esc(title)}) /Producer (Appointment Platform) >>".encode())

    out = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = []
    for i, obj in enumerate(objects, 1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n".encode() + obj + b"\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode()
    for off in offsets:
        out += f"{off:010d} 00000 n \n".encode()
    out += f"trailer\n<< /Size {len(objects) + 1} /Root {catalog} 0 R /Info {info} 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    return bytes(out)
