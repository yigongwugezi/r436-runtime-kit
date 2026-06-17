import json
from pathlib import Path
from typing import Any

from app.config import settings


class CourseCatalog:
    """Loads course knowledge-base metadata from knowledge_base/courses."""

    def __init__(self, root: Path | None = None) -> None:
        self.root = root or settings.project_root / "knowledge_base" / "courses"

    def list_courses(self) -> list[dict[str, Any]]:
        courses = []
        if not self.root.exists():
            return courses

        for course_file in sorted(self.root.glob("*/course.json")):
            course = self._load_course_file(course_file)
            if course:
                courses.append(self._summary(course))
        return courses

    def get_course(self, course_id: str) -> dict[str, Any] | None:
        course_file = self.root / course_id / "course.json"
        course = self._load_course_file(course_file)
        if course is None:
            return None
        return {
            **course,
            "outline": self._read_optional_text(self.root / course_id / "outline.md"),
            "chapter_count": len(course.get("chapters", [])),
        }

    def match_course(self, text: str | None, default: str = "ai_intro") -> dict[str, Any] | None:
        query = (text or "").strip().lower()
        if not query:
            return self.get_course(default)

        best_course: dict[str, Any] | None = None
        best_score = 0
        for course in self.list_courses():
            detail = self.get_course(str(course.get("course_id")))
            if detail is None:
                continue
            score = self._match_score(query, detail)
            if score > best_score:
                best_score = score
                best_course = detail

        # Only return a course if we actually matched — no silent fallback
        if best_score > 0:
            return best_course
        return None

    def load_chapter(self, course_id: str, chapter_id: str) -> dict[str, Any] | None:
        course = self.get_course(course_id)
        if course is None:
            return None

        chapter = next(
            (item for item in course.get("chapters", []) if str(item.get("chapter_id")) == str(chapter_id)),
            None,
        )
        if chapter is None:
            return None

        file_path = self.root / course_id / str(chapter.get("file", ""))
        return {
            **chapter,
            "course_id": course_id,
            "content": self._read_optional_text(file_path),
        }

    def _load_course_file(self, path: Path) -> dict[str, Any] | None:
        if not path.exists():
            return None
        with path.open("r", encoding="utf-8") as file:
            data = json.load(file)
        if not data.get("course_id"):
            data["course_id"] = path.parent.name
        return data

    def _summary(self, course: dict[str, Any]) -> dict[str, Any]:
        return {
            "course_id": course.get("course_id"),
            "course_name": course.get("course_name"),
            "difficulty": course.get("difficulty", "introductory"),
            "description": course.get("description", ""),
            "chapter_count": len(course.get("chapters", [])),
            "target_students": course.get("target_students", []),
            "aliases": course.get("aliases", []),
        }

    def _match_score(self, query: str, course: dict[str, Any]) -> int:
        score = 0
        fields = [
            str(course.get("course_id", "")),
            str(course.get("course_name", "")),
            str(course.get("description", "")),
            " ".join(str(item) for item in course.get("aliases", [])),
            " ".join(str(item) for item in course.get("target_students", [])),
        ]
        for chapter in course.get("chapters", []):
            fields.append(str(chapter.get("title", "")))
            fields.extend(str(item) for item in chapter.get("prerequisites", []))

        for field in fields:
            normalized = field.lower()
            if not normalized:
                continue
            if query == normalized:
                score += 100
            # Only allow substring match for longer queries (>= 4 chars)
            # to prevent short words like "历史" from matching "发展历史"
            elif len(query) >= 4 and (query in normalized or normalized in query):
                score += 30

        token_aliases = {
            "ai": "人工智能",
            "ml": "机器学习",
            "nn": "神经网络",
            "nlp": "自然语言处理",
            "ds": "数据结构",
        }
        expanded = token_aliases.get(query)
        if expanded:
            score += self._match_score(expanded, course) // 2

        return score

    def _read_optional_text(self, path: Path) -> str:
        if not path.exists() or not path.is_file():
            return ""
        return path.read_text(encoding="utf-8")


course_catalog = CourseCatalog()
