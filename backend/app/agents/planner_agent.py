import re
from math import ceil
from typing import Any

from app.agents.base import BaseAgent


class PlannerAgent(BaseAgent):
    agent_id = "planner_agent"
    agent_name = "学习路径规划智能体"

    def run(self, context: dict[str, Any]) -> dict[str, Any]:
        weak_points = list(context.get("diagnosis", {}).get("weak_knowledge_points", []))
        if not weak_points:
            return {
                "learning_path": self.mock_data["learning_path"],
                "agent_step": self.agent_step(),
            }

        profile = context.get("profile", {})
        total_days = self._infer_days(str(context.get("user_message", "")), profile)
        stage_count = min(4, len(weak_points), max(1, total_days))
        days_per_stage = max(1, ceil(total_days / stage_count))

        learning_path = []
        for index, point in enumerate(weak_points[:stage_count], start=1):
            start_day = (index - 1) * days_per_stage + 1
            end_day = min(total_days, index * days_per_stage)
            learning_path.append(
                {
                    "stage_id": f"stage_{index}",
                    "title": self._stage_title(index, str(point.get("name", "重点知识点"))),
                    "duration": f"第 {start_day}-{end_day} 天" if start_day != end_day else f"第 {start_day} 天",
                    "goal": self._goal(point, profile),
                    "tasks": self._tasks(point, profile, index),
                    "resource_types": self._resource_types(profile, index),
                    "source": "agent_generated",
                }
            )

        if total_days <= 3:
            learning_path.append(
                {
                    "stage_id": f"stage_{len(learning_path) + 1}",
                    "title": "快速复盘与考前检查",
                    "duration": f"第 {total_days} 天",
                    "goal": "用练习题和错题复盘检查核心概念，保证短周期学习能形成可交付结果。",
                    "tasks": ["完成重点练习题", "整理易错点清单", "回看高优先级章节讲义"],
                    "resource_types": ["quiz", "reading"],
                    "source": "agent_generated",
                }
            )

        return {
            "learning_path": learning_path,
            "agent_step": self.agent_step(),
        }

    def _infer_days(self, message: str, profile: dict[str, Any]) -> int:
        text = " ".join(
            str(part)
            for part in [
                message,
                profile.get("learning_goal", {}).get("value", ""),
                profile.get("learning_progress", {}).get("value", ""),
            ]
        )
        text = self._normalize_cn_number_time(text)
        hour_match = re.search(r"(\d+)\s*(?:小时|h|H)", text)
        if hour_match and "每天" not in text:
            return max(1, ceil(int(hour_match.group(1)) / 24))
        day_match = re.search(r"(\d+)\s*(?:天|日)", text)
        if day_match:
            return max(1, min(60, int(day_match.group(1))))
        week_match = re.search(r"(\d+)\s*(?:周|星期)", text)
        if week_match:
            return max(1, min(60, int(week_match.group(1)) * 7))
        if "两周" in text or "二周" in text:
            return 14
        if "一周" in text:
            return 7
        return 14

    def _normalize_cn_number_time(self, text: str) -> str:
        number_map = {
            "半": "0",
            "一": "1",
            "二": "2",
            "两": "2",
            "三": "3",
            "四": "4",
            "五": "5",
            "六": "6",
            "七": "7",
            "八": "8",
            "九": "9",
            "十": "10",
        }
        for cn, digit in number_map.items():
            text = re.sub(rf"{cn}\s*(天|日|周|星期|个月|小时|分钟)", rf"{digit}\1", text)
        return text

    def _stage_title(self, index: int, point_name: str) -> str:
        prefixes = ["补齐基础", "攻克核心", "专项练习", "综合复盘"]
        return f"{prefixes[min(index - 1, len(prefixes) - 1)]}：{point_name}"

    def _goal(self, point: dict[str, Any], profile: dict[str, Any]) -> str:
        prerequisites = "、".join(str(item) for item in point.get("prerequisites", []) if item)
        base = f"理解并掌握 {point.get('name', '该知识点')} 的核心概念、典型题型和常见误区。"
        if prerequisites:
            base += f" 同时补齐前置要求：{prerequisites}。"
        if "考试" in str(profile.get("learning_goal", {}).get("value", "")):
            base += " 重点服务考试通过和基础题型稳定得分。"
        return base

    def _tasks(self, point: dict[str, Any], profile: dict[str, Any], index: int) -> list[str]:
        name = str(point.get("name", "知识点"))
        tasks = [
            f"阅读《{name}》个性化讲义",
            f"完成 {name} 的概念辨析练习",
        ]
        preference = str(profile.get("cognitive_style", {}).get("value", ""))
        if any(word in preference for word in ["代码", "实操", "实验"]):
            tasks.append(f"运行一个与 {name} 相关的代码/伪代码案例")
        elif any(word in preference for word in ["图解", "思维导图"]):
            tasks.append(f"查看 {name} 的结构图并复述知识关系")
        else:
            tasks.append(f"整理 {name} 的易错点清单")
        if index > 1:
            tasks.append("复盘上一阶段错题和未掌握概念")
        return tasks

    def _resource_types(self, profile: dict[str, Any], index: int) -> list[str]:
        preference = str(profile.get("cognitive_style", {}).get("value", ""))
        types = ["lecture", "quiz"]
        if any(word in preference for word in ["图解", "思维导图"]):
            types.append("mindmap")
        if any(word in preference for word in ["代码", "实操", "实验"]):
            types.append("practice")
        if index == 1:
            types.append("reading")
        return list(dict.fromkeys(types))
