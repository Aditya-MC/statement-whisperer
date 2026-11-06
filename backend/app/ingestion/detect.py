"""File type detection from magic bytes, with the extension as a tiebreaker."""

from __future__ import annotations

import enum
from pathlib import PurePath


class FileType(enum.StrEnum):
    csv = "csv"
    xlsx = "xlsx"
    pdf = "pdf"
    image = "image"
    xls = "xls"
    unknown = "unknown"


#: File types the current phase can ingest.
SUPPORTED = frozenset({FileType.csv, FileType.xlsx})


class UnsupportedFileError(ValueError):
    """The file is not a type we can ingest (yet)."""


def detect_file_type(filename: str | None, data: bytes) -> FileType:
    head = data[:8]
    if head.startswith(b"%PDF"):
        return FileType.pdf
    if head.startswith(b"PK\x03\x04"):
        # XLSX is a zip; other zip containers (docx, plain .zip) are not statements.
        return (
            FileType.xlsx
            if b"xl/" in data[:4096] or _ext(filename) == ".xlsx"
            else (FileType.unknown)
        )
    if head.startswith(b"\xd0\xcf\x11\xe0"):
        return FileType.xls
    if head.startswith((b"\x89PNG", b"\xff\xd8\xff", b"GIF8", b"II*\x00", b"MM\x00*")):
        return FileType.image
    if _looks_like_text(data[:4096]):
        return FileType.csv
    return FileType.unknown


def ensure_supported(file_type: FileType) -> None:
    if file_type in SUPPORTED:
        return
    hints = {
        FileType.pdf: "PDF statements are planned for a later phase; export CSV/XLSX for now.",
        FileType.image: "Scanned statements are planned for a later phase.",
        FileType.xls: "Legacy .xls is not supported; re-save the file as .xlsx or .csv.",
    }
    raise UnsupportedFileError(hints.get(file_type, "Unrecognized file type; upload CSV or XLSX."))


def _ext(filename: str | None) -> str:
    return PurePath(filename).suffix.lower() if filename else ""


def _looks_like_text(chunk: bytes) -> bool:
    if not chunk or b"\x00" in chunk:
        return False
    for enc in ("utf-8", "cp1252"):
        try:
            chunk.decode(enc)
            return True
        except UnicodeDecodeError:
            # A multi-byte UTF-8 char may be cut at the chunk boundary.
            if enc == "utf-8":
                try:
                    chunk[:-3].decode(enc)
                    return True
                except UnicodeDecodeError:
                    continue
    return False
