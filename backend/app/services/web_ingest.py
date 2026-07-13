"""Web content ingestion — fetch URLs, extract text, index into FAISS."""

from __future__ import annotations

import asyncio
import logging
import os
import re
import uuid
from dataclasses import dataclass, field
from typing import Any

from llama_index.core.schema import TextNode

from app.rag.config import rag_config
from app.rag.embedder import create_embedding_model

logger = logging.getLogger(__name__)


@dataclass
class IngestResult:
    url: str
    title: str = ""
    ok: bool = False
    chunks: int = 0
    error: str = ""


# ── URL fetch ──────────────────────────────────────────────────────────────

async def _fetch_url(url: str, timeout: float = 15.0) -> tuple[str, str]:
    """Fetch a URL and return (markdown_text, title). Uses DeepTutor's web_fetch."""
    try:
        from deeptutor.tools.web_fetch import fetch_url_as_markdown

        outcome = await fetch_url_as_markdown(url, max_chars=50000, timeout_s=timeout)
        if outcome.ok and outcome.markdown:
            return outcome.markdown, outcome.title or ""
        return "", outcome.error or "fetch returned no content"
    except ImportError:
        pass

    # Fallback: basic httpx fetch + simple HTML stripping
    try:
        import httpx

        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.get(url, headers={"User-Agent": "EduAgent/1.0"}, follow_redirects=True)
            resp.raise_for_status()
            html = resp.text
            # Crude tag stripping
            text = re.sub(r"<script[^>]*>.*?</script>", "", html, flags=re.DOTALL | re.IGNORECASE)
            text = re.sub(r"<style[^>]*>.*?</style>", "", text, flags=re.DOTALL | re.IGNORECASE)
            text = re.sub(r"<[^>]+>", " ", text)
            text = re.sub(r"\s+", " ", text).strip()
            title_match = re.search(r"<title>(.*?)</title>", html, re.IGNORECASE)
            title = title_match.group(1).strip() if title_match else ""
            return text, title
    except Exception as e:
        return "", str(e)


# ── Text chunking ──────────────────────────────────────────────────────────

def _chunk_text(text: str, title: str, url: str) -> list[TextNode]:
    """Chunk markdown text into TextNode objects for indexing."""
    from llama_index.core import Document
    from llama_index.core.node_parser import SentenceSplitter

    splitter = SentenceSplitter(
        chunk_size=rag_config.chunk_size,
        chunk_overlap=rag_config.chunk_overlap,
        separator=" ".join(rag_config.chinese_separators),
    )

    nodes = splitter.get_nodes_from_documents([
        Document(text=text)
    ])

    web_id = uuid.uuid4().hex[:12]
    for i, node in enumerate(nodes):
        node.id_ = f"web_{web_id}_{i:04d}"
        node.metadata.update({
            "source": "web_ingest",
            "url": url,
            "title": title,
            "web_id": web_id,
            "chunk_index": i,
        })

    return nodes


# ── Main ingest pipeline ───────────────────────────────────────────────────

async def ingest_url(url: str) -> IngestResult:
    """Fetch a URL, chunk its content, embed, and insert into the FAISS index.

    Returns an IngestResult with status and chunk count.
    """
    # 1. Fetch
    markdown, title = await _fetch_url(url)
    if not markdown or len(markdown) < 100:
        return IngestResult(url=url, title=title, ok=False, error="内容过短或抓取失败")

    # 2. Chunk
    nodes = _chunk_text(markdown, title, url)
    if not nodes:
        return IngestResult(url=url, title=title, ok=False, error="切块结果为空")

    # 3. Embed — reuse the query engine's already-loaded embedding model
    try:
        from app.rag.query_engine import rag_query_engine

        rag_query_engine.wait_until_ready(timeout=30.0)
        if not rag_query_engine.is_ready():
            return IngestResult(url=url, title=title, ok=False, error="RAG 引擎未就绪")

        # Access the loaded embedding model from the index
        embed_model = rag_query_engine._index._embed_model
        if embed_model is None:
            from app.rag.embedder import create_embedding_model
            embed_model = create_embedding_model(rag_config)
        embeddings = embed_model.get_text_embedding_batch(
            [node.get_content() for node in nodes],
            show_progress=False,
        )
        for node, embedding in zip(nodes, embeddings):
            node.embedding = embedding
    except Exception as e:
        return IngestResult(url=url, title=title, ok=False, error=f"嵌入失败: {e}")

    # 4. Insert into index + persist (engine already verified ready above)
    try:
        rag_query_engine.insert_nodes(nodes)
    except Exception as e:
        return IngestResult(url=url, title=title, ok=False, error=f"索引写入失败: {e}")

    return IngestResult(url=url, title=title or url, ok=True, chunks=len(nodes))


# Synchronous wrapper
def ingest_url_sync(url: str) -> IngestResult:
    return asyncio.run(ingest_url(url))
