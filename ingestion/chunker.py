from dataclasses import dataclass

from ingestion.parser import ParsedDoc

# Target sizes in approximate tokens (1 word ≈ 1.33 tokens by OpenAI's rule of thumb).
# Swap this module for a tiktoken-backed implementation in environments with
# network access; the interface (chunk_doc, Chunk, CHUNK_SIZE, CHUNK_OVERLAP) stays the same.
CHUNK_SIZE = 500       # tokens
CHUNK_OVERLAP = 50     # tokens

_TOKENS_PER_WORD = 4 / 3
_WORDS_PER_CHUNK = round(CHUNK_SIZE / _TOKENS_PER_WORD)    # ≈ 375
_WORDS_OVERLAP = round(CHUNK_OVERLAP / _TOKENS_PER_WORD)   # ≈ 37


@dataclass
class Chunk:
    chunk_index: int
    page_start: int
    page_end: int
    text: str
    token_count: int   # estimated


def chunk_doc(doc: ParsedDoc) -> list[Chunk]:
    # Build a flat list of (word, page_number) pairs across all pages.
    flat: list[tuple[str, int]] = []
    for page in doc.pages:
        for word in page.text.split():
            flat.append((word, page.number))

    if not flat:
        return []

    words = [w for w, _ in flat]
    page_nums = [p for _, p in flat]

    chunks: list[Chunk] = []
    start = 0
    while start < len(words):
        end = min(start + _WORDS_PER_CHUNK, len(words))
        span_words = words[start:end]
        span_pages = page_nums[start:end]
        estimated_tokens = round(len(span_words) * _TOKENS_PER_WORD)

        chunks.append(Chunk(
            chunk_index=len(chunks),
            page_start=span_pages[0],
            page_end=span_pages[-1],
            text=" ".join(span_words),
            token_count=estimated_tokens,
        ))

        if end == len(words):
            break
        start = end - _WORDS_OVERLAP

    return chunks
