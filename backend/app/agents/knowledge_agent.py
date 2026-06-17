from typing import Any

from app.agents.base import BaseAgent
from app.services.course_catalog import course_catalog


class KnowledgeAgent(BaseAgent):
    agent_id = "knowledge_agent"
    agent_name = "知识库检索智能体"

    def run(self, context: dict[str, Any]) -> dict[str, Any]:
        course_id = str(context.get("course_id") or self.mock_data.get("course_id") or "ai_intro")
        # Only fall back to ai_intro if the course_id itself isn't already a catalog course;
        # for custom/unknown courses we build the virtual context below
        course = course_catalog.get_course(course_id)
        if course is None and not course_id.startswith("custom_"):
            course = course_catalog.get_course("ai_intro") or {}
        if course is None:
            course = {}

        message = str(context.get("user_message", ""))
        profile = context.get("profile", {})
        query = " ".join(
            [
                message,
                str(profile.get("knowledge_base", {}).get("value", "")),
                str(profile.get("weak_points", {}).get("value", "")),
                str(profile.get("learning_goal", {}).get("value", "")),
                str(profile.get("interests", {}).get("value", "")),
            ]
        ).lower()

        chapters = list(course.get("chapters", []))

        # If no chapters (virtual/custom course), generate a generic knowledge point from the course name
        if not chapters:
            # Extract the actual topic name from profile or user message
            course_name = (
                course.get("course_name")
                or profile.get("interests", {}).get("value", "")
                or profile.get("learning_goal", {}).get("value", "")
                or course_id
            )
            retrieved_points = [
                {
                    "point_id": f"{course_id}_topic_1",
                    "chapter_id": "01",
                    "name": str(course_name).strip(),
                    "priority": "high",
                    "difficulty": "medium",
                    "prerequisites": [],
                    "content_excerpt": f"用户自选学习主题：{course_name}",
                }
            ]
            return {
                "knowledge_context": {
                    "course_id": course_id,
                    "course_name": course_name,
                    "retrieved_points": retrieved_points,
                    "source": "user_provided_topic",
                },
                "agent_step": self.agent_step(),
            }

        # Normal flow: score and select chapters from the course catalog
        scored = sorted(
            ((self._score_chapter(query, chapter), chapter) for chapter in chapters),
            key=lambda item: item[0],
            reverse=True,
        )
        selected = [chapter for score, chapter in scored if score > 0][:4] or chapters[:4]

        retrieved_points = []
        for index, chapter in enumerate(selected, start=1):
            chapter_id = str(chapter.get("chapter_id", index)).zfill(2)
            detail = course_catalog.load_chapter(str(course.get("course_id", course_id)), chapter_id) or chapter
            retrieved_points.append(
                {
                    "point_id": f"{course.get('course_id', course_id)}_{chapter_id}",
                    "chapter_id": chapter_id,
                    "name": chapter.get("title", f"第 {index} 章"),
                    "priority": "high" if index <= 2 else "medium",
                    "difficulty": chapter.get("difficulty", "medium"),
                    "prerequisites": chapter.get("prerequisites", []),
                    "content_excerpt": self._excerpt(str(detail.get("content", ""))),
                }
            )

        return {
            "knowledge_context": {
                "course_id": course.get("course_id", course_id),
                "course_name": course.get("course_name", course_id),
                "retrieved_points": retrieved_points,
                "source": "course_knowledge_base",
            },
            "agent_step": self.agent_step(),
        }

    def _score_chapter(self, query: str, chapter: dict[str, Any]) -> int:
        title = str(chapter.get("title", "")).lower()
        prerequisites = " ".join(str(item).lower() for item in chapter.get("prerequisites", []))
        text = f"{title} {prerequisites}"
        score = 0

        for token in query.replace("，", " ").replace("。", " ").split():
            if len(token) >= 2 and token in text:
                score += 3

        if any(word in query for word in ["零基础", "不会", "入门"]) and chapter.get("difficulty") == "easy":
            score += 3
        if any(word in query for word in ["考试", "复习"]) and chapter.get("difficulty") in {"easy", "medium"}:
            score += 2
        if any(word in query for word in ["代码", "实验", "实操"]) and chapter.get("difficulty") == "medium":
            score += 1
        return score

    def _excerpt(self, content: str, limit: int = 220) -> str:
        compact = " ".join(line.strip() for line in content.splitlines() if line.strip())
        return compact[:limit]
