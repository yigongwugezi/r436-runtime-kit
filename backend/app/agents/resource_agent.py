from typing import Any

from app.agents.base import BaseAgent


class ResourceAgent(BaseAgent):
    agent_id = "resource_agent"
    agent_name = "学习资源生成智能体"

    def run(self, context: dict[str, Any]) -> dict[str, Any]:
        path = list(context.get("learning_path", []))
        points = list(context.get("diagnosis", {}).get("weak_knowledge_points", []))
        course = context.get("knowledge_context", {})
        profile = context.get("profile", {})

        if not path or not points:
            return {
                "resources": [],
                "agent_step": self.agent_step(),
            }

        resources = [
            self._lecture(points, course, profile),
            self._mindmap(points, course),
            self._quiz(points, profile),
            self._reading(points, course),
            self._practice(points, profile),
            self._video_script(points, course),
        ]
        resources = self._scope_resource_ids(resources, str(context.get("session_id") or ""))

        return {
            "resources": resources,
            "agent_step": self.agent_step(),
        }

    def _scope_resource_ids(self, resources: list[dict[str, Any]], session_id: str) -> list[dict[str, Any]]:
        if not session_id:
            return resources
        for item in resources:
            resource_id = str(item.get("resource_id", ""))
            if resource_id and not resource_id.startswith(f"{session_id}_"):
                item["resource_id"] = f"{session_id}_{resource_id}"
        return resources

    def _lecture(self, points: list[dict[str, Any]], course: dict[str, Any], profile: dict[str, Any]) -> dict[str, Any]:
        first = points[0]
        names = "、".join(str(point.get("name")) for point in points[:3])
        learner_base = profile.get("knowledge_base", {}).get("value", "暂未明确")
        content = (
            f"## {course.get('course_name', '课程')}个性化讲义\n\n"
            f"### 学习对象\n\n当前基础：{learner_base}\n\n"
            f"### 本轮重点\n\n本轮优先学习：{names}。\n\n"
            "### 学习建议\n\n"
            "1. 先读概念定义，确认每个术语解决的是什么问题。\n"
            "2. 再看例子或图解，把抽象概念落到具体场景。\n"
            "3. 最后做 3-5 道小题，检查是否真的会用。\n\n"
            f"### 第一个突破口\n\n从“{first.get('name')}”开始，因为它是当前路径中优先级最高的知识点。"
        )
        return {
            "resource_id": "res_lecture_001",
            "type": "lecture",
            "title": f"{first.get('name')}入门讲义",
            "description": f"根据学生画像和课程知识库生成，优先覆盖 {names}。",
            "content_format": "markdown",
            "content": content,
            "related_stage_id": "stage_1",
            "source": "agent_generated",
            "quality_status": "passed",
        }

    def _mindmap(self, points: list[dict[str, Any]], course: dict[str, Any]) -> dict[str, Any]:
        root = course.get("course_name", "个性化学习路径")
        lines = ["mindmap", f"  root(({root}))"]
        for point in points[:5]:
            lines.append(f"    {self._safe_mermaid(str(point.get('name', '知识点')))}")
            for prerequisite in point.get("prerequisites", [])[:2]:
                lines.append(f"      前置：{self._safe_mermaid(str(prerequisite))}")
            lines.append(f"      优先级：{point.get('priority', 'medium')}")
        return {
            "resource_id": "res_mindmap_001",
            "type": "mindmap",
            "title": f"{root}知识结构图",
            "description": "把当前检索到的课程章节、前置依赖和优先级组织成思维导图。",
            "content_format": "mermaid",
            "content": "\n".join(lines),
            "related_stage_id": "stage_1",
            "source": "agent_generated",
            "quality_status": "passed",
        }

    def _quiz(self, points: list[dict[str, Any]], profile: dict[str, Any]) -> dict[str, Any]:
        goal = str(profile.get("learning_goal", {}).get("value", ""))
        items = []
        for index, point in enumerate(points[:4], start=1):
            name = str(point.get("name", f"知识点 {index}"))
            items.append(
                {
                    "question_id": f"q_{index:03d}",
                    "question_type": "short_answer" if index % 2 == 0 else "single_choice",
                    "stem": f"请说明“{name}”主要解决什么问题，并举一个学习或考试中的应用场景。",
                    "options": [] if index % 2 == 0 else ["概念理解", "机械记忆", "无关内容", "跳过不学"],
                    "answer": "围绕核心概念、使用场景、常见误区进行回答即可。",
                    "explanation": f"该题用于检查学生是否真正理解 {name}，而不是只记住名称。",
                    "difficulty": "medium" if point.get("priority") == "high" else "easy",
                    "knowledge_point": name,
                }
            )
        return {
            "resource_id": "res_quiz_001",
            "type": "quiz",
            "title": "个性化基础检测题",
            "description": f"围绕当前学习目标生成，目标：{goal or '查漏补缺'}。",
            "content_format": "json",
            "items": items,
            "related_stage_id": "stage_1",
            "source": "agent_generated",
            "quality_status": "passed",
        }

    def _reading(self, points: list[dict[str, Any]], course: dict[str, Any]) -> dict[str, Any]:
        bullet_lines = "\n".join(
            f"{index}. 复习 {point.get('name')}：先看定义，再看易错点，最后做一道例题。"
            for index, point in enumerate(points[:5], start=1)
        )
        return {
            "resource_id": "res_reading_001",
            "type": "reading",
            "title": "拓展阅读与复盘建议",
            "description": "把课程知识库中的重点章节转成可执行的阅读顺序。",
            "content_format": "markdown",
            "content": f"## 阅读顺序\n\n{bullet_lines}\n\n## 防幻觉提醒\n\n关键定义和公式请回到课程教材或课堂课件核对。",
            "related_stage_id": "stage_2",
            "source": "agent_generated",
            "quality_status": "passed",
        }

    def _practice(self, points: list[dict[str, Any]], profile: dict[str, Any]) -> dict[str, Any]:
        first = points[0]
        target = str(first.get("name", "核心知识点"))
        content = (
            f"## 实操任务：用代码或伪代码理解 {target}\n\n"
            "### 任务目标\n\n"
            f"把“{target}”转换成一个可以运行、画图或手推的小例子。\n\n"
            "### 建议步骤\n\n"
            "1. 写出输入、处理过程和输出。\n"
            "2. 用最小样例手动跑一遍。\n"
            "3. 标出最容易出错的边界条件。\n\n"
            "```python\n"
            "def learn_step(example):\n"
            "    # TODO: replace this with the course-specific operation\n"
            "    return example\n\n"
            "print(learn_step('demo'))\n"
            "```\n"
        )
        return {
            "resource_id": "res_practice_001",
            "type": "practice",
            "title": f"{target}实操案例",
            "description": "按学生偏好生成的可执行/可改写实践任务。",
            "content_format": "markdown",
            "content": content,
            "related_stage_id": "stage_1",
            "source": "agent_generated",
            "quality_status": "passed",
        }

    def _video_script(self, points: list[dict[str, Any]], course: dict[str, Any]) -> dict[str, Any]:
        first = points[0]
        return {
            "resource_id": "res_multimodal_001",
            "type": "multimodal",
            "title": f"多模态讲解脚本：{first.get('name')}",
            "description": "先生成视频/动画脚本，后续可接入 SeeDance 等多模态工具。",
            "content_format": "markdown",
            "content": (
                f"## 60 秒讲解脚本：{first.get('name')}\n\n"
                "1. 画面：展示课程总标题和本节关键词。旁白：今天先解决一个关键问题。\n"
                f"2. 画面：突出“{first.get('name')}”。旁白：它是当前路径中的优先知识点。\n"
                "3. 画面：列出前置知识和常见误区。旁白：先补前置，再做练习。\n"
                "4. 画面：出现一道小题或代码片段。旁白：用一个例子检查是否真正理解。\n"
                "5. 画面：给出下一步学习任务。旁白：完成讲义、练习和复盘。"
            ),
            "related_stage_id": "stage_2",
            "source": "agent_generated",
            "quality_status": "passed",
        }

    def _safe_mermaid(self, text: str) -> str:
        return text.replace("(", "（").replace(")", "）").replace(":", "：")
