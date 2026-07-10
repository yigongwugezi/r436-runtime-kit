"""Knowledge retrieval agent — RAG-first, course catalog fallback, with optional LLM query expansion."""

from typing import Any

from app.agents.base import BaseAgent


class KnowledgeAgent(BaseAgent):
    agent_id = "knowledge_agent"
    agent_name = "知识库检索智能体"

    def _expand_query(self, query: str) -> str:
        """Use LLM to expand short or ambiguous queries for better RAG retrieval."""
        if not self.llm_client or len(query) > 80:
            return query
        try:
            expanded = self.llm_client.chat(
                messages=[{
                    "role": "user",
                    "content": (
                        f"将以下学习相关的查询扩展为2-3个更具体的搜索关键词，"
                        f"用空格分隔，只输出关键词：{query}"
                    ),
                }],
                temperature=0,
            )
            expanded = str(expanded).strip()
            return expanded if expanded and len(expanded) > len(query) else query
        except Exception:
            return query

    def run(self, context: dict[str, Any]) -> dict[str, Any]:
        message = str(context.get("user_message", ""))
        profile = context.get("profile", {}) or {}
        course_id = str(context.get("course_id", "") or "")

        # Build query from context
        query_parts = [message]
        if isinstance(profile, dict):
            for key in ("knowledge_base", "learning_goal", "interest_direction"):
                v = profile.get(key, {})
                val = str(v.get("value", "") if isinstance(v, dict) else v).strip()
                if val:
                    query_parts.append(val)
        query = " ".join(query_parts).strip()

        # ── RAG retrieval (primary) ──
        retrieved_points = []
        source = "course_knowledge_base"
        try:
            from app.rag.query_engine import rag_query_engine

            if rag_query_engine.is_ready():
                expanded_query = self._expand_query(query)
                response = rag_query_engine.search(expanded_query or query, top_k=5)
                if response and response.results:
                    for i, r in enumerate(response.results):
                        retrieved_points.append({
                            "point_id": f"rag_{i}",
                            "chapter_id": f"rag_{i:02d}",
                            "name": str(r.title or r.id or f"知识点{i+1}")[:60],
                            "priority": "high" if i < 2 else "medium",
                            "difficulty": "medium",
                            "content_excerpt": str(r.text)[:300],
                        })
                    source = "rag_retrieval"
        except Exception:
            pass

        # ── Course catalog fallback ──
        if not retrieved_points:
            from app.services.course_catalog import course_catalog
            course = course_catalog.get_course(course_id) or {}
            chapters = list(course.get("chapters", []))
            course_name = course.get("course_name", course_id)
            if chapters:
                for i, ch in enumerate(chapters[:4]):
                    retrieved_points.append({
                        "point_id": f"{course_id}_{i:02d}",
                        "chapter_id": str(ch.get("chapter_id", i)).zfill(2),
                        "name": ch.get("title", f"第{i+1}章"),
                        "priority": "high" if i < 2 else "medium",
                        "difficulty": ch.get("difficulty", "medium"),
                        "content_excerpt": str(ch.get("content", ""))[:300],
                    })
            else:
                retrieved_points.append({
                    "point_id": f"{course_id}_topic_1",
                    "chapter_id": "01",
                    "name": course_name or "目标课程",
                    "priority": "high",
                    "difficulty": "medium",
                    "content_excerpt": f"学习主题：{course_name or course_id}",
                })
            source = "course_knowledge_base"

        return {
            "knowledge_context": {
                "course_id": course_id,
                "course_name": str(course.get("course_name", course_id)) if 'course' in dir() else "",
                "retrieved_points": retrieved_points,
                "source": source,
            },
            "agent_step": self.agent_step(),
        }
