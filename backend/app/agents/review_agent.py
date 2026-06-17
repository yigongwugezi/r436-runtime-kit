from typing import Any

from app.agents.base import BaseAgent


class ReviewAgent(BaseAgent):
    agent_id = "review_agent"
    agent_name = "质量审核智能体"

    required_resource_types = {"lecture", "mindmap", "quiz", "reading", "practice"}
    blocked_terms = {
        "代写作业",
        "考试作弊",
        "泄题",
        "绕过监考",
        "违法",
        "攻击系统",
        "窃取",
    }

    def run(self, context: dict[str, Any]) -> dict[str, Any]:
        checks = [
            self._check_profile(context),
            self._check_knowledge_grounding(context),
            self._check_learning_path(context),
            self._check_resource_coverage(context),
            self._check_resource_content(context),
            self._check_content_safety(context),
        ]
        quality_status = "passed" if all(check["status"] == "passed" for check in checks) else "needs_review"

        return {
            "review": {
                "quality_status": quality_status,
                "checks": checks,
                "summary": self._summary(checks),
                "anti_hallucination": {
                    "enabled": True,
                    "strategy": "基于课程知识库检索结果生成路径和资源，并对资源覆盖度、空内容、敏感内容和来源标记进行审核。",
                    "knowledge_source": context.get("knowledge_context", {}).get("source", "unknown"),
                },
            },
            "agent_step": self.agent_step(),
        }

    def _check_profile(self, context: dict[str, Any]) -> dict[str, Any]:
        profile = context.get("profile", {})
        filled = [
            key
            for key, value in profile.items()
            if isinstance(value, dict) and str(value.get("value", "")).strip()
        ]
        return self._check(
            "profile_completeness",
            "画像完整度检查",
            len(filled) >= 5,
            f"已形成 {len(filled)} 个画像维度，可支撑第一版学习方案。",
            f"画像维度只有 {len(filled)} 个，建议继续补充学生背景、目标、基础和偏好。",
        )

    def _check_knowledge_grounding(self, context: dict[str, Any]) -> dict[str, Any]:
        knowledge = context.get("knowledge_context", {})
        points = knowledge.get("retrieved_points", [])
        ok = knowledge.get("source") == "course_knowledge_base" and len(points) > 0
        return self._check(
            "knowledge_grounding",
            "知识库依据检查",
            ok,
            f"已从课程知识库检索到 {len(points)} 个相关知识点。",
            "未发现有效课程知识库依据，生成结果需要人工复核。",
        )

    def _check_learning_path(self, context: dict[str, Any]) -> dict[str, Any]:
        path = context.get("learning_path", [])
        ok = bool(path) and all(stage.get("tasks") and stage.get("goal") for stage in path)
        inverted = any(self._has_inverted_duration(str(stage.get("duration", ""))) for stage in path)
        return self._check(
            "path_structure",
            "学习路径结构检查",
            ok and not inverted,
            f"已生成 {len(path)} 个学习阶段，阶段目标和任务完整。",
            "学习路径为空、阶段任务不完整，或存在不合理时间范围。",
        )

    def _check_resource_coverage(self, context: dict[str, Any]) -> dict[str, Any]:
        resources = context.get("resources", [])
        types = {str(item.get("type")) for item in resources}
        missing = sorted(self.required_resource_types - types)
        return self._check(
            "resource_coverage",
            "资源类型覆盖检查",
            not missing,
            f"已覆盖资源类型：{', '.join(sorted(types))}。",
            f"缺少资源类型：{', '.join(missing)}。",
        )

    def _check_resource_content(self, context: dict[str, Any]) -> dict[str, Any]:
        resources = context.get("resources", [])
        empty = [
            item.get("resource_id", item.get("title", "unknown"))
            for item in resources
            if not str(item.get("content") or item.get("items") or "").strip()
        ]
        mocked = [
            item.get("resource_id", item.get("title", "unknown"))
            for item in resources
            if item.get("source") == "mock"
        ]
        ok = not empty and not mocked
        message = "资源均有正文或题目内容，且来源不是 mock。"
        fail = []
        if empty:
            fail.append(f"空内容资源：{', '.join(str(item) for item in empty)}")
        if mocked:
            fail.append(f"仍为 mock 的资源：{', '.join(str(item) for item in mocked)}")
        return self._check("resource_integrity", "资源完整度检查", ok, message, "；".join(fail))

    def _check_content_safety(self, context: dict[str, Any]) -> dict[str, Any]:
        text = " ".join(
            [
                str(context.get("diagnosis", {}).get("summary", "")),
                " ".join(str(stage.get("goal", "")) for stage in context.get("learning_path", [])),
                " ".join(
                    f"{item.get('title', '')} {item.get('description', '')} {item.get('content', '')}"
                    for item in context.get("resources", [])
                ),
            ]
        )
        hits = sorted(term for term in self.blocked_terms if term in text)
        return self._check(
            "content_safety",
            "内容安全检查",
            not hits,
            "未发现明显违规或不适合教育场景的内容。",
            f"发现需要人工复核的词：{', '.join(hits)}。",
        )

    def _check(self, check_id: str, name: str, ok: bool, passed: str, failed: str) -> dict[str, str]:
        return {
            "check_id": check_id,
            "name": name,
            "status": "passed" if ok else "needs_review",
            "message": passed if ok else failed,
        }

    def _has_inverted_duration(self, duration: str) -> bool:
        numbers = [int(item) for item in duration.replace("第", "").replace("天", "").split("-") if item.isdigit()]
        return len(numbers) == 2 and numbers[0] > numbers[1]

    def _summary(self, checks: list[dict[str, str]]) -> str:
        failed = [check for check in checks if check["status"] != "passed"]
        if not failed:
            return "生成结果已通过结构完整性、知识库依据、资源覆盖度和内容安全检查。"
        names = "、".join(check["name"] for check in failed)
        return f"生成结果需要人工复核，重点关注：{names}。"
