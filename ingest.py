#!/usr/bin/env python3
"""
Ingest PDFs into the condo RAG document store.

Usage:
    python ingest.py docs/               # walk a directory
    python ingest.py docs/bylaws.pdf     # single file

Set DATABASE_URL in .env or the environment before running.
"""
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

from ingestion.chunker import chunk_doc
from ingestion.parser import parse_pdf
from ingestion.store import doc_exists, get_conn, insert_chunks, insert_document

# Keywords used to infer doc_type from filename or parent directory name.
_DOC_TYPE_KEYWORDS = [
    "bylaw", "rule", "regulation", "insurance",
    "financial", "budget", "minutes", "maintenance", "contract", "vendor",
]


def _infer_doc_type(path: Path) -> str | None:
    haystack = (path.stem + " " + path.parent.name).lower()
    for kw in _DOC_TYPE_KEYWORDS:
        if kw in haystack:
            return kw
    return None


def ingest_file(path: Path, conn) -> None:
    print(f"  {path}")
    doc = parse_pdf(str(path))

    if doc_exists(conn, doc.sha256):
        print(f"    skip — already ingested (sha256 {doc.sha256[:8]}…)")
        return

    chunks = chunk_doc(doc)
    if not chunks:
        print(f"    skip — no text extracted (scanned PDF with no OCR fallback)")
        return

    doc_type = _infer_doc_type(path)
    doc_id = insert_document(conn, doc, doc_type)
    insert_chunks(conn, doc_id, chunks)
    conn.commit()

    print(f"    inserted {len(chunks)} chunks (doc_id={doc_id}, type={doc_type or 'unknown'})")


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: python ingest.py <docs-dir-or-file>", file=sys.stderr)
        sys.exit(1)

    target = Path(sys.argv[1])
    if not target.exists():
        print(f"Error: {target} does not exist", file=sys.stderr)
        sys.exit(1)

    paths = [target] if target.is_file() else sorted(target.rglob("*.pdf"))
    if not paths:
        print("No PDF files found.")
        return

    print(f"Ingesting {len(paths)} file(s)…")
    conn = get_conn()
    try:
        for path in paths:
            ingest_file(path, conn)
    finally:
        conn.close()

    print("Done.")


if __name__ == "__main__":
    main()
