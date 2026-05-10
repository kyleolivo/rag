import hashlib
import sys
from dataclasses import dataclass, field

import pypdf

SCANNED_CHAR_THRESHOLD = 50  # pages with fewer extracted chars are flagged as scanned


@dataclass
class Page:
    number: int  # 0-indexed
    text: str


@dataclass
class ParsedDoc:
    path: str
    sha256: str
    page_count: int
    pages: list[Page]
    title: str | None


def parse_pdf(path: str) -> ParsedDoc:
    sha256 = _file_hash(path)
    reader = pypdf.PdfReader(path)

    pages: list[Page] = []
    scanned: list[int] = []

    for i, page in enumerate(reader.pages):
        text = page.extract_text() or ""
        if len(text.strip()) < SCANNED_CHAR_THRESHOLD:
            scanned.append(i)
        pages.append(Page(number=i, text=text))

    if scanned:
        pct = len(scanned) / len(pages) * 100
        print(
            f"  WARNING {path}: {len(scanned)}/{len(pages)} pages appear scanned "
            f"({pct:.0f}%) — text extraction may be incomplete.",
            file=sys.stderr,
        )

    title: str | None = None
    if reader.metadata and reader.metadata.title:
        title = reader.metadata.title

    return ParsedDoc(
        path=path,
        sha256=sha256,
        page_count=len(pages),
        pages=pages,
        title=title,
    )


def _file_hash(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(65536), b""):
            h.update(block)
    return h.hexdigest()
