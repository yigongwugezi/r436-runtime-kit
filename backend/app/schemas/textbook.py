"""Pydantic schemas for textbook API."""

from __future__ import annotations

from pydantic import BaseModel, Field


# ── Chapter / Section structure (mirrors chapters_json) ───────────────


class TextbookSectionSchema(BaseModel):
    """A single section within a textbook chapter."""

    section_id: str = Field(default="")
    title: str = Field(default="")
    order: int = Field(default=0)
    start_page: int = Field(default=1)
    end_page: int = Field(default=1)
    estimated_minutes: int = Field(default=45)
    knowledge_points: list[str] = Field(default_factory=list)


class TextbookChapterSchema(BaseModel):
    """A single chapter within a textbook."""

    chapter_id: str = Field(default="")
    title: str = Field(default="")
    order: int = Field(default=0)
    start_page: int = Field(default=1)
    end_page: int = Field(default=1)
    sections: list[TextbookSectionSchema] = Field(default_factory=list)


# ── Response schemas ──────────────────────────────────────────────────


class TextbookResponse(BaseModel):
    """Public textbook metadata returned to the frontend."""

    id: str
    subject_id: str = Field(default="")
    title: str | None = None
    author: str | None = None
    filename: str = ""
    file_size_bytes: int = 0
    page_count: int = 0
    status: str = "uploading"  # uploading | processing | ready | error
    parse_error: str | None = None
    chapters_json: list[TextbookChapterSchema] | None = None
    created_at: int = 0
    updated_at: int = 0


class TextbookTOCResponse(BaseModel):
    """Full TOC for a textbook."""

    textbook: TextbookResponse
    chapters: list[TextbookChapterSchema] = Field(default_factory=list)


class TextbookContentResponse(BaseModel):
    """Extracted markdown content for a textbook section or page range."""

    textbook_id: str
    section_id: str | None = None
    page_start: int = 0
    page_end: int = 0
    content: str = ""


class TextbookListResponse(BaseModel):
    """List of textbooks for resource library."""

    textbooks: list[TextbookResponse] = Field(default_factory=list)
