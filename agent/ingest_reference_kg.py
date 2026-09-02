"""
GraphRAG ingestion — REF/ reference books → Neo4j.

Translates the REF/*.md quant-finance corpus into :Book -> :Chapter -> :Section
nodes with COVERS links to existing :Concept nodes, creates fulltext indexes
and (when configured) computes embedding properties + a vector index so the
Financial-Engineer chat can do hybrid GraphRAG retrieval in Neo4j.
"""
from __future__ import annotations

import os
import re
from pathlib import Path

import requests
from loguru import logger

from common.graph import get_db

REF_DIR = Path(os.getenv("REF_DIR", "REF"))
MAX_SECTION_CHARS = int(os.getenv("REF_MAX_SECTION_CHARS", "3000"))

BOOK_FILE_MAP: list[tuple[str, str]] = [
    ("aat-ebook-20170711.md", "aat-2017"),
    ("HULL.md", "hull-8ed"),
    ("tradmarkets.md", "tradmarkets"),
    ("alternativeinstruments.md", "alternativeinstruments"),
    ("credit_risk_and_financing.md", "credit_risk"),
    ("LIQUIDITY AND REGULATION.md", "liquidity_regulation"),
    ("MODEL FAILURE AND CRISES .md", "model_failure"),
    ("VOLATILITY AND CORRELATION.md", "volatility_correlation"),
    ("Module_5_Non_linearity_Leverage_and_Mean_Reversion.md", "module5"),
]


class _Section:
    __slots__ = ("chapter", "title", "body", "section_id")

    def __init__(self, chapter, title, body, section_id):
        self.chapter = chapter
        self.title = title
        self.body = body
        self.section_id = section_id


def _slug(text):
    s = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return (s or "section")[:80]


def _split_aat(text):
    out = []
    cur_chapter = "front-matter"
    cur_title = ""
    buf = []

    def _flush():
        nonlocal buf, cur_title, cur_chapter
        body = "\n".join(buf).strip()
        if body and len(body) >= 40:
            out.append(_Section(cur_chapter, cur_title.strip(), body[:MAX_SECTION_CHARS],
                                f"aat-{_slug(cur_chapter)}-{_slug(cur_title)}"))
        buf = []

    for raw in text.splitlines():
        line = raw.strip()
        if line.startswith("### "):
            _flush()
            cur_title = line[4:].strip()
        elif line.startswith("## ") and ("Chapter" in line or "Part" in line):
            _flush()
            cur_chapter = line[3:].strip()
            cur_title = cur_chapter
        elif line.startswith("# ") and "Contents" not in line:
            _flush()
            cur_chapter = line[2:].strip()
            cur_title = cur_chapter
        else:
            buf.append(line)
    _flush()
    return out


def _split_hull(text):
    out = []
    heading_rx = re.compile(r"^#{1,4}\s+(.+)$")
    cur_chapter = "hull-general"
    cur_title = ""
    buf = []

    def _flush():
        nonlocal buf, cur_title, cur_chapter
        body = "\n".join(buf).strip()
        if body and len(body) >= 40:
            out.append(_Section(cur_chapter, (cur_title or "section").strip(),
                                body[:MAX_SECTION_CHARS],
                                f"hull-{_slug(cur_chapter)}-{_slug(cur_title or 'section')}"))
        buf = []

    for raw in text.splitlines():
        m = heading_rx.match(raw.strip())
        if m:
            _flush()
            cur_title = m.group(1).strip()
        line = raw.strip()
        if not line:
            continue
        buf.append(line)
        if len("\n".join(buf)) >= MAX_SECTION_CHARS:
            _flush()
    _flush()
    return out


def _split_mindmap(text):
    out = []
    cur_chapter = "root"
    cur_title = ""
    buf = []

    def _flush():
        nonlocal buf, cur_title, cur_chapter
        body = "\n".join(buf).strip()
        if body and len(body) >= 40:
            out.append(_Section(cur_chapter, (cur_title or "section").strip(),
                                body[:MAX_SECTION_CHARS],
                                f"wm-{_slug(cur_chapter)}-{_slug(cur_title or 'section')}"))
        buf = []

    for raw in text.splitlines():
        line = raw.strip()
        if line.startswith("### "):
            _flush()
            cur_title = line[4:].strip()
        elif line.startswith("## "):
            _flush()
            cur_chapter = line[3:].strip()
            cur_title = cur_chapter
        else:
            buf.append(line)
    _flush()
    return out


def parse_book(text, book_id):
    if book_id == "aat-2017":
        return _split_aat(text)
    if book_id == "hull-8ed":
        return _split_hull(text)
    if text.count("## ") > 0:
        return _split_mindmap(text)
    return _split_hull(text)


def _embed(texts):
    key = os.getenv("EMBEDDING_API_KEY", "").strip()
    if not key or not texts:
        return None
    url = os.getenv("EMBEDDING_BASE_URL", "https://api.jina.ai/v1").rstrip("/") + "/embeddings"
    model = os.getenv("EMBEDDING_MODEL", "jina-embeddings-v3")
    batch = int(os.getenv("EMBEDDING_BATCH_SIZE", "16"))
    dim = int(os.getenv("EMBEDDING_DIM", "1024"))
    out = []
    try:
        for i in range(0, len(texts), batch):
            chunk = texts[i : i + batch]
            r = requests.post(url, headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                              json={"model": model, "input": chunk}, timeout=120)
            r.raise_for_status()
            items = r.json()["data"]
            out.extend([it["embedding"][:dim] for it in sorted(items, key=lambda x: x["index"])])
        return out
    except Exception as e:
        logger.warning(f"embedding failed ({e}) — continuing with fulltext-only graph retrieval")
        return None


def _ensure_indexes(db):
    try:
        db.execute_and_fetch(
            "CREATE FULLTEXT INDEX ref_section_fulltext IF NOT EXISTS FOR (n:Section) ON EACH [n.title, n.body]"
        )
    except Exception as e:
        logger.warning(f"fulltext index (section) note: {e}")
    try:
        db.execute_and_fetch(
            "CREATE FULLTEXT INDEX ref_concept_fulltext IF NOT EXISTS FOR (n:Concept) ON EACH [n.name, n.definition]"
        )
    except Exception as e:
        logger.warning(f"fulltext index (concept) note: {e}")
    if os.getenv("EMBEDDING_API_KEY", "").strip():
        try:
            dim = int(os.getenv("EMBEDDING_DIM", "1024"))
            db.execute_and_fetch(
                "CREATE VECTOR INDEX ref_section_vector IF NOT EXISTS FOR (n:Section) ON (n.embedding) "
                f"OPTIONS {{indexConfig: {{`vector.dimensions`: {dim}, `vector.similarity_function`: 'cosine'}}}}"
            )
        except Exception as e:
            logger.warning(f"vector index note: {e}")


def ingest():
    db = get_db()
    summary = {"sections": 0, "concepts": 0, "book_edges": 0, "embedded": 0}
    concepts = {r["name"] for r in db.execute_and_fetch("MATCH (c:Concept) RETURN c.name AS name")}
    logger.info(f"loaded {len(concepts)} existing concepts for COVERS matching")
    _ensure_indexes(db)

    # PHASE 1: parse all books into memory (no db writes yet)
    books = []
    for fname, book_id in BOOK_FILE_MAP:
        path = REF_DIR / fname
        if not path.exists():
            logger.warning(f"missing REF file: {path} — skipping")
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        sections = parse_book(text, book_id)
        if not sections:
            logger.warning(f"no sections parsed for {fname}")
            continue
        logger.info(f"{fname}: {len(sections)} sections -> {book_id}")
        book_rows = list(db.execute_and_fetch("MATCH (b:Book {id: $id}) RETURN b.id AS id", {"id": book_id}))
        if not book_rows:
            logger.warning(f"Book node {book_id} not found in graph — skipping")
            continue
        bodies = [s.body for s in sections]
        vecs = _embed(bodies) if os.getenv("EMBEDDING_API_KEY", "").strip() else None
        for idx, sec in enumerate(sections):
            props = {"id": f"{book_id}::{sec.section_id}", "book": book_id, "chapter": sec.chapter,
                     "title": sec.title, "body": sec.body, "seq": idx, "source": str(path)}
            if vecs:
                props["embedding"] = vecs[idx]
                summary["embedded"] += 1
            books.append((book_id, props, sec))

    # PHASE 2: write everything in batches (avoid lazy-generator clobbering)
    BATCH = 120
    total = len(books)
    for i in range(0, total, BATCH):
        batch = books[i:i + BATCH]
        # 1) MERGE sections
        for _, props, _ in batch:
            list(db.execute_and_fetch("MERGE (s:Section {id: $id}) SET s += $props", {"id": props["id"], "props": props}))
            summary["sections"] += 1
        # 2) Book->Section edges
        for book_id, props, _ in batch:
            list(db.execute_and_fetch(
                "MATCH (b:Book {id: $book}), (s:Section {id: $sid}) MERGE (b)-[:HAS_CHAPTER]->(s)",
                {"book": book_id, "sid": props["id"]}))
            summary["book_edges"] += 1
        # 3) COVERS edges
        for _, props, sec in batch:
            hay = f"{sec.title} {sec.body[:400]}"
            matched = 0
            for cname in concepts:
                if cname.lower() in hay.lower() and len(cname) >= 4:
                    try:
                        list(db.execute_and_fetch(
                            "MATCH (s:Section {id: $sid}), (c:Concept {name: $cname}) MERGE (s)-[:COVERS]->(c)",
                            {"sid": props["id"], "cname": cname}))
                        matched += 1
                        summary["concepts"] += 1
                    except Exception:
                        pass
                    if matched >= 6:
                        break
        logger.info(f"wrote batch {i + len(batch)}/{total}")
    logger.success(f"ingest complete: {summary}")
    return summary


if __name__ == "__main__":
    ingest()
