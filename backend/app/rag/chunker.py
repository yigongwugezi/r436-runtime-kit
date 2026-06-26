"""Chinese-text chunking for Wikipedia articles.

The pipeline:

1. **Clean** — strip wiki language-variant markers, normalise whitespace.
2. **Pre-split** — insert paragraph breaks at Chinese sentence boundaries
   (``。！？；``) so the downstream LlamaIndex splitter respects them.
3. **Chunk** — split into overlapping ``Document`` nodes using LlamaIndex's
   ``SentenceSplitter`` with paragraph-aware configuration.

Each chunk carries metadata (wiki id, title, url, source file, chunk index)
so that search results are traceable back to the original article.
"""

from __future__ import annotations

import logging
import re
from typing import Any

from llama_index.core import Document
from llama_index.core.node_parser import SentenceSplitter

from app.rag.config import RAGConfig

logger = logging.getLogger("app.rag.chunker")

# Regex that matches Chinese Wikipedia language-variant markers:
#   -{zh-cn:...;zh-tw:...;zh-hk:...}-
# Some variants use spaces: -{ ... }-
_VARIANT_PATTERN = re.compile(r"- ?\{[^}]*\} ?-")

# Chinese sentence-ending / clause-separating punctuation.
# We insert paragraph breaks at these boundaries so the chunker prefers
# them as split points.
_CHINESE_SENTENCE_ENDS = re.compile(r"([。！？；])(?=\S)")


def clean_text(text: str) -> str:
    """Remove wiki formatting artifacts from article text.

    Handles:
    - Language-variant markers: ``-{zh-cn:A;zh-tw:B}-``
    - Excessive newlines (collapse 3+ to double newline)
    - Leading / trailing whitespace
    """
    text = _VARIANT_PATTERN.sub("", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _pre_split_chinese_sentences(text: str) -> str:
    """Insert ``\\n\\n`` after Chinese sentence-ending punctuation.

    This makes the downstream ``SentenceSplitter`` (which respects
    paragraph breaks) split at natural Chinese sentence boundaries
    rather than mid-phrase.
    """
    # Replace sentence-ending punctuation followed by a non-whitespace char
    # with the punctuation + double-newline.
    return _CHINESE_SENTENCE_ENDS.sub(r"\1\n\n", text)


def clean_all_records(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Apply :func:`clean_text` to every record's ``text`` field in-place."""
    for r in records:
        r["text"] = clean_text(r.get("text", ""))
    return records


def _build_chunker(config: RAGConfig) -> SentenceSplitter:
    """Create a LlamaIndex sentence splitter tuned for Chinese.

    Uses paragraph-aware splitting (``\\n\\n``) combined with a secondary
    newline separator.  Chinese sentence boundaries have already been
    converted to paragraph breaks by :func:`_pre_split_chinese_sentences`.
    """
    return SentenceSplitter(
        chunk_size=config.chunk_size,
        chunk_overlap=config.chunk_overlap,
        paragraph_separator="\n\n",
        separator="\n",
        include_metadata=True,
    )


def chunk_records(
    records: list[dict[str, Any]],
    config: RAGConfig,
) -> list[Document]:
    """Split cleaned records into LlamaIndex ``Document`` chunks.

    Each chunk is a :class:`~llama_index.core.Document` whose ``text`` is
    the chunk content and whose ``metadata`` carries provenance info:

    - ``wiki_id`` — original Wikipedia page id
    - ``title``   — article title
    - ``url``     — Wikipedia URL
    - ``source_file`` — originating ``wiki_*`` file (relative)
    - ``chunk_index`` — zero-based position within the article
    """
    splitter = _build_chunker(config)
    documents: list[Document] = []

    for rec in records:
        text = rec.get("text", "")
        if not text.strip():
            continue

        # Pre-split at Chinese sentence boundaries for better chunking
        text = _pre_split_chinese_sentences(text)

        doc = Document(
            text=text,
            metadata={
                "wiki_id": rec.get("id", ""),
                "title": rec.get("title", ""),
                "url": rec.get("url", ""),
                "source_file": rec.get("_source_file", ""),
            },
        )
        # SentenceSplitter.get_nodes_from_documents splits one Document
        # into multiple Node objects when the text exceeds chunk_size.
        nodes = splitter.get_nodes_from_documents([doc])

        for idx, node in enumerate(nodes):
            node.metadata["chunk_index"] = str(idx)
            documents.append(node)

    logger.info(
        "Chunked %d records → %d document nodes (chunk_size=%d, overlap=%d)",
        len(records),
        len(documents),
        config.chunk_size,
        config.chunk_overlap,
    )
    return documents
