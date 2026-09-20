"""Archive search over Markdown corpora (FTS5 + jieba tokenization).

The archive is whatever the caller points at: a workspace holding past
patent projects, or one project's ``reference/`` folder. The FTS5 table is
built per call — a personal corpus is small enough that the insert cost
beats maintaining an index file — but the expensive half, reading and
jieba-tokenizing each file, is cached per path keyed by its mtime, so the
interview's rolling re-searches over the same archive skip re-tokenizing
unchanged files. The query tokens drive an FTS5 BM25 match whose hits return
path, title, and a centered snippet. Subdirectories that never hold prose
(``exports/``, ``review/`` caches, VCS/tool dirs) are skipped.
"""

from __future__ import annotations

import re
import sqlite3
from pathlib import Path

import jieba

#: Directory names that never hold searchable prose.
SKIPPED_DIRS = {"exports", ".git", "node_modules", "__pycache__", ".venv"}

#: Hard cap on indexed files; a personal archive should stay far below it.
MAX_FILES = 2000

#: Title fallback: the first Markdown heading, else the file stem.
_HEADING = re.compile(r"^#\s+(.+)$", re.MULTILINE)

#: Tokens shorter than this are dropped from both sides (Chinese stopword-ish).
MIN_TOKEN_CHARS = 2

#: Per-file tokenization cache: path -> (mtime, title, tokens). Survives for
#: the server process lifetime; a changed mtime re-tokenizes, and a corpus
#: twice the file cap drops the whole cache rather than growing unbounded.
_TOKEN_CACHE: dict[str, tuple[float, str, str]] = {}
MAX_TOKEN_CACHE_ENTRIES = 2 * MAX_FILES


def tokenize(text: str) -> str:
    """Segment text for FTS5: jieba cuts, ASCII-lowercased, joined by spaces.

    @param text: free text (Chinese or mixed).
    @returns the space-joined token stream FTS5 stores and matches against.
    """
    tokens = []
    for raw in jieba.cut_for_search(text):
        token = raw.strip().lower()
        if len(token) >= MIN_TOKEN_CHARS:
            tokens.append(token)
    return " ".join(tokens)


def collect_markdown(archive_dir: str) -> list[Path]:
    """Collect searchable Markdown files under the archive root, capped.

    @param archive_dir: the archive root directory.
    @returns up to :data:`MAX_FILES` file paths in stable walk order.
    """
    root = Path(archive_dir)
    if not root.is_dir():
        return []
    files: list[Path] = []
    for path in sorted(root.rglob("*.md")):
        if len(files) >= MAX_FILES:
            break
        if any(part in SKIPPED_DIRS for part in path.parts):
            continue
        if path.is_file():
            files.append(path)
    return files


def _indexed_document(path: Path) -> tuple[str, str]:
    """Return one file's ``(title, tokens)`` pair, reusing the mtime-keyed cache.

    @param path: a collected Markdown file.
    @returns the heading (or stem) title and the space-joined token stream.
    """
    mtime = path.stat().st_mtime
    cached = _TOKEN_CACHE.get(str(path))
    if cached is not None and cached[0] == mtime:
        return cached[1], cached[2]
    body = path.read_text(encoding="utf-8", errors="replace")
    heading = _HEADING.search(body)
    title = heading.group(1).strip() if heading else path.stem
    tokens = tokenize(body)
    if len(_TOKEN_CACHE) >= MAX_TOKEN_CACHE_ENTRIES:
        _TOKEN_CACHE.clear()
    _TOKEN_CACHE[str(path)] = (mtime, title, tokens)
    return title, tokens


def search_archive(query: str, archive_dir: str, limit: int = 8) -> list[dict[str, str]]:
    """Search the archive's Markdown files for the query.

    @param query: free-text query (Chinese or mixed).
    @param archive_dir: the archive root directory.
    @param limit: maximum hits; validated to 1-50.
    @returns hits ranked by BM25: ``{"path", "title", "snippet"}`` entries.
    @raises ValueError: an empty query, a missing archive directory, or an
        out-of-range limit.
    """
    if not query.strip():
        raise ValueError("empty query")
    if not 1 <= limit <= 50:
        raise ValueError(f"limit must be 1-50, got {limit}")
    files = collect_markdown(archive_dir)
    if not files:
        raise ValueError(f"no Markdown files to search under: {archive_dir}")
    connection = sqlite3.connect(":memory:")
    connection.execute("CREATE VIRTUAL TABLE docs USING fts5(path, title, body, tokenize='unicode61')")
    for path in files:
        title, tokens = _indexed_document(path)
        connection.execute(
            "INSERT INTO docs(path, title, body) VALUES (?, ?, ?)",
            (str(path), title, tokens),
        )
    match = " OR ".join(f'"{token}"' for token in tokenize(query).split())
    if match == "":
        raise ValueError("query produced no searchable tokens")
    rows = connection.execute(
        "SELECT path, title, snippet(docs, 2, '「', '」', '…', 12), bm25(docs) "
        "FROM docs WHERE docs MATCH ? ORDER BY bm25(docs) LIMIT ?",
        (match, limit),
    ).fetchall()
    connection.close()
    return [{"path": row[0], "title": row[1], "snippet": row[2]} for row in rows]
