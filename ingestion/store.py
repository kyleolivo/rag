import os

import psycopg2
import psycopg2.extras

from ingestion.chunker import Chunk
from ingestion.parser import ParsedDoc


def get_conn():
    return psycopg2.connect(os.environ["DATABASE_URL"])


def doc_exists(conn, sha256: str) -> bool:
    with conn.cursor() as cur:
        cur.execute("SELECT 1 FROM documents WHERE sha256 = %s", (sha256,))
        return cur.fetchone() is not None


def insert_document(conn, doc: ParsedDoc, doc_type: str | None) -> int:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO documents (path, title, doc_type, sha256, page_count)
            VALUES (%s, %s, %s, %s, %s)
            RETURNING id
            """,
            (doc.path, doc.title, doc_type, doc.sha256, doc.page_count),
        )
        return cur.fetchone()[0]


def insert_chunks(conn, document_id: int, chunks: list[Chunk]) -> None:
    rows = [
        (document_id, c.chunk_index, c.page_start, c.page_end, c.text, c.token_count)
        for c in chunks
    ]
    with conn.cursor() as cur:
        psycopg2.extras.execute_values(
            cur,
            """
            INSERT INTO chunks (document_id, chunk_index, page_start, page_end, text, token_count)
            VALUES %s
            """,
            rows,
        )
