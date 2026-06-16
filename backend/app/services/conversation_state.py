import re
import time
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.orm import Session

from app.db.engine import SessionLocal
from app.db.repository import (
    delete_session,
    get_last_intent,
    get_messages,
    get_or_create_session,
    save_message,
    save_profile_snapshot,
    save_learning_path,
    save_resource,
    get_latest_profile,
    get_latest_learning_path,
    get_resources as repo_get_resources,
)


PROFILE_FIELD_DEFS: dict[str, dict[str, Any]] = {
    "background": {
        "label": "身份/专业背景",
        "question": "你现在的年级、专业或身份是什么？",
    },
    "target_course": {
        "label": "目标课程/知识方向",
        "question": "你这次最想学习哪门课或哪个知识方向？",
    },
    "knowledge_base": {
        "label": "已有基础",
        "question": "你之前学过哪些相关基础，掌握到什么程度？",
    },
    "weak_points": {
        "label": "薄弱点",
        "question": "你觉得目前最卡的知识点或题型是什么？",
    },
    "learning_goal": {
        "label": "学习目标",
        "question": "你希望最后达到什么效果，比如考试、项目、入门或查漏补缺？",
    },
    "time_budget": {
        "label": "时间安排",
        "question": "你打算用几天完成，每天大概能学多久？",
    },
    "preference": {
        "label": "学习偏好",
        "question": "你更喜欢文字讲解、图解、视频脚本、练习题，还是代码实操？",
    },
}

SUPPLEMENTAL_FIELD_DEFS: dict[str, dict[str, str]] = {
    "personal_background": {
        "label": "个人背景补充",
        "question": "你还有哪些可能影响学习安排的个人情况？",
    },
    "identity_note": {
        "label": "身份补充",
        "question": "你的专业、年级或学习场景是什么？",
    },
    "interest_note": {
        "label": "兴趣/动机补充",
        "question": "你对哪些应用方向或项目更感兴趣？",
    },
}

CORE_FIELDS = {"background", "target_course", "knowledge_base"}
PLAN_READY_FIELDS = {"background", "target_course", "knowledge_base"}
LOW_VALUE_BACKGROUND_WORDS = {
    "男生",
    "女生",
    "男",
    "女",
    "男孩子",
    "女孩子",
    "普通人",
    "学生",
    "大学生",
}
BACKGROUND_VALUE_HINTS = {
    "专业",
    "工程",
    "计算机",
    "软件",
    "人工智能",
    "电子",
    "信息",
    "自动化",
    "数学",
    "统计",
    "大一",
    "大二",
    "大三",
    "大四",
    "研究生",
    "本科",
    "高职",
    "课程",
}
COURSE_STOPWORDS = {
    "方案",
    "学习方案",
    "路径",
    "学习路径",
    "计划",
    "学习计划",
}


@dataclass
class ConversationState:
    session_id: str
    messages: list[dict[str, Any]] = field(default_factory=list)
    facts: dict[str, str] = field(default_factory=dict)
    supplemental_facts: dict[str, list[str]] = field(default_factory=dict)
    last_updated_fields: list[str] = field(default_factory=list)
    last_updated_supplemental_fields: list[str] = field(default_factory=list)
    last_intent: dict[str, Any] | None = None
    last_result: dict[str, Any] | None = None
    updated_at: float = field(default_factory=time.time)


class ConversationStore:
    """Session state manager with in-memory cache and DB persistence.

    When ``_db_enabled`` is True, session data is loaded from / saved to
    the database.  The in-memory cache serves as a fast-access layer;
    all mutating methods flush to DB immediately.
    """

    def __init__(self) -> None:
        self._sessions: dict[str, ConversationState] = {}
        self._db_enabled: bool = False

    # ── DB lifecycle ─────────────────────────────────────────────────

    def enable_db(self) -> None:
        """Enable database persistence.

        Called once at application startup.  After this call every
        ``get``, ``append_message``, ``set_intent``, ``set_result`` and
        ``reset`` will read from / write to the database.
        """
        self._db_enabled = True

    def _db_session(self) -> Session:
        """Create a new short-lived DB session."""
        return SessionLocal()

    # ── Hydration helpers ─────────────────────────────────────────────

    def _hydrate_from_db(self, state: ConversationState) -> None:
        """Load messages, intent and last_result from the database into *state*."""
        try:
            db = self._db_session()
            # Messages
            db_messages = get_messages(db, state.session_id)
            state.messages = [
                {
                    "role": m.role,
                    "content": m.content,
                    "timestamp": int(m.created_at.timestamp() * 1000) if m.created_at else int(time.time() * 1000),
                }
                for m in db_messages
            ]
            # Last intent
            state.last_intent = get_last_intent(db, state.session_id)
            # Last result (reconstruct from latest snapshots)
            profile = get_latest_profile(db, state.session_id)
            path = get_latest_learning_path(db, state.session_id)
            db_resources = repo_get_resources(db, state.session_id)
            if profile or path or db_resources:
                result: dict[str, Any] = {}
                if profile:
                    # Reconstruct dict format from list-of-dict rows
                    raw_dims = profile.dimensions or {}
                    if isinstance(raw_dims, list):
                        result["profile"] = {
                            dim.get("key", f"dim_{idx}"): {
                                "label": dim.get("label", ""),
                                "value": dim.get("value", ""),
                                "confidence": dim.get("confidence", 0.75),
                            }
                            for idx, dim in enumerate(raw_dims)
                        }
                    else:
                        result["profile"] = raw_dims
                    result["diagnosis"] = {"weak_knowledge_points": profile.weaknesses or []}
                    result["session_id"] = state.session_id
                    result["preferences"] = profile.preferences or {}
                if path:
                    result["learning_path"] = path.stages or []
                    result["course_id"] = path.course_id
                    result["course"] = {"course_id": path.course_id, "course_name": path.course_name}
                if db_resources:
                    result["resources"] = [
                        {
                            "resource_id": r.id,
                            "type": r.type,
                            "title": r.title,
                            "description": r.description or "",
                            "content": r.content or "",
                            "content_format": "markdown",
                            "source": "db",
                            "related_stage_id": r.session_id,
                        }
                        for r in db_resources
                    ]
                state.last_result = result if result else None
            # Re-extract facts by replaying user messages through extract_facts
            state.facts.clear()
            state.supplemental_facts.clear()
            for msg in state.messages:
                if msg.get("role") == "user":
                    self.extract_facts(state, str(msg.get("content", "")))
        finally:
            db.close()

    # ── Public API (unchanged signatures) ─────────────────────────────

    def get(self, session_id: str | None) -> ConversationState:
        sid = (session_id or "frontend_session_001").strip() or "frontend_session_001"
        if sid not in self._sessions:
            state = ConversationState(session_id=sid)
            self._sessions[sid] = state
            if self._db_enabled:
                self._hydrate_from_db(state)
        return self._sessions[sid]

    def reset(self, session_id: str | None) -> ConversationState:
        sid = (session_id or "frontend_session_001").strip() or "frontend_session_001"
        self._sessions[sid] = ConversationState(session_id=sid)
        if self._db_enabled:
            try:
                db = self._db_session()
                delete_session(db, sid)
                # Re-create empty session row
                get_or_create_session(db, sid)
            finally:
                db.close()
        return self._sessions[sid]

    def append_message(self, session_id: str | None, role: str, content: str) -> ConversationState:
        state = self.get(session_id)
        state.messages.append(
            {
                "role": role,
                "content": content,
                "timestamp": int(time.time() * 1000),
            }
        )
        state.updated_at = time.time()
        if role == "user":
            self.extract_facts(state, content)

        if self._db_enabled:
            try:
                db = self._db_session()
                save_message(db, state.session_id, role, content)
            finally:
                db.close()
        return state

    def set_intent(self, session_id: str | None, intent: dict[str, Any]) -> None:
        state = self.get(session_id)
        state.last_intent = intent
        state.updated_at = time.time()

    def set_result(self, session_id: str | None, result: dict[str, Any]) -> None:
        state = self.get(session_id)
        state.last_result = result
        self.merge_result_profile(state, result)
        state.updated_at = time.time()

        if self._db_enabled:
            try:
                db = self._db_session()
                # Save profile snapshot
                profile_data = result.get("profile", {})
                dimensions_list = [
                    {
                        "key": key,
                        "label": item.get("label", key) if isinstance(item, dict) else key,
                        "value": str(item.get("value", "")) if isinstance(item, dict) else str(item),
                        "confidence": item.get("confidence", 0.75) if isinstance(item, dict) else 0.75,
                    }
                    for key, item in profile_data.items()
                ]
                weaknesses_list = [
                    {"name": point.get("name", ""), "priority": point.get("priority", "medium")}
                    for point in result.get("diagnosis", {}).get("weak_knowledge_points", [])
                ]
                readiness = self.readiness(state)
                save_profile_snapshot(
                    db, state.session_id,
                    dimensions=dimensions_list,
                    weaknesses=weaknesses_list,
                    readiness_score=readiness.get("score"),
                )

                # Save learning path if present
                if result.get("learning_path"):
                    path_data = {
                        "id": f"path_{result.get('course_id', state.session_id)}",
                        "course_id": result.get("course_id", ""),
                        "course_name": (result.get("course") or {}).get("course_name", ""),
                        "stages": result.get("learning_path"),
                        "overallProgress": 18,
                        "estimatedDays": 14,
                    }
                    save_learning_path(db, state.session_id, path_data)

                # Save resources if present
                for item in result.get("resources", []):
                    save_resource(db, state.session_id, {
                        "id": item.get("resource_id", f"res_{time.time()}"),
                        "type": item.get("type", "lecture"),
                        "title": item.get("title", "学习资源"),
                        "description": item.get("description", ""),
                        "content": item.get("content", ""),
                        "tags": [item.get("content_format", "markdown"), item.get("source", "mock")],
                    })
            finally:
                db.close()

    # ── Fact extraction (unchanged, pure processing logic) ─────────────

    def extract_facts(self, state: ConversationState, message: str) -> None:
        text = message.strip()
        state.last_updated_fields = []
        state.last_updated_supplemental_fields = []
        if not text:
            return

        lower = text.lower()

        def set_fact(key: str, value: str) -> None:
            cleaned = self._clean_time_value(value) if key == "time_budget" else self._clean_fact_value(value)
            if not cleaned:
                return
            if state.facts.get(key) != cleaned:
                state.facts[key] = cleaned
                state.last_updated_fields.append(key)

        def add_supplemental(key: str, value: str) -> None:
            cleaned = self._clean_fact_value(value)
            if not cleaned:
                return
            values = state.supplemental_facts.setdefault(key, [])
            if cleaned not in values:
                values.append(cleaned)
                state.last_updated_supplemental_fields.append(key)

        background_patterns = [
            r"我是一名([^，。,.!?！？]{2,30})",
            r"我是([^，。,.!?！？]{2,30})",
            r"本人是([^，。,.!?！？]{2,30})",
            r"我的专业是([^，。,.!?！？]{2,30})",
        ]
        for pattern in background_patterns:
            match = re.search(pattern, text)
            if match:
                background_value = match.group(1)
                if self._is_learning_background(background_value):
                    set_fact("background", background_value)
                else:
                    add_supplemental("personal_background", background_value)
                break

        if "运动员" in text:
            add_supplemental("identity_note", "运动员")

        if any(word in text for word in ["感兴趣", "喜欢", "想做", "方向"]):
            interest_match = re.search(r"(?:对|喜欢|想做)([^，。,.!?！？]{2,30})(?:感兴趣|方向|项目)?", text)
            if interest_match and "学习" not in interest_match.group(1):
                add_supplemental("interest_note", interest_match.group(1))

        course_match = re.search(
            r"(?:想学习|想学|想系统学习|我要学|希望学|准备学|入门|复习|掌握|了解)([^，。,.!?！？]{2,30})",
            text,
        )
        if course_match:
            set_fact("target_course", course_match.group(1))

        goal_course_match = re.search(r"学懂([^，。,.!?！？]{2,30})", text)
        if goal_course_match:
            set_fact("target_course", goal_course_match.group(1))

        exam_review_match = re.search(r"(?:考研|考试)?复习([^，。,.!?！？]{2,30})", text)
        if exam_review_match:
            set_fact("target_course", exam_review_match.group(1))

        zero_base_course_match = re.search(r"([A-Za-z+#一-鿿]{2,20})零基础", text)
        if zero_base_course_match:
            set_fact("target_course", zero_base_course_match.group(1))

        strengths, weaknesses = self._extract_knowledge_levels(text)
        if strengths:
            set_fact("knowledge_base", "；".join(strengths))
        elif any(word in text for word in ["基础", "学过", "会", "不会", "薄弱", "差", "一般", "还行"]):
            base_match = re.search(r"([^，。,.!?！？]{1,24}基础(?:一般|较弱|薄弱|还可以|不错|很好|较好)?)", text)
            set_fact("knowledge_base", base_match.group(1) if base_match else text)

        if weaknesses:
            set_fact("weak_points", "；".join(weaknesses))
        elif any(word in text for word in ["薄弱", "不会", "卡", "难", "不懂", "错误", "错题"]):
            weak_match = re.search(r"([^，。,.!?！？]{1,30})(?:比较|很|有点)?(?:薄弱|不会|不懂|卡|难)", text)
            if weak_match:
                set_fact("weak_points", f"{weak_match.group(1)}较薄弱")
            else:
                set_fact("weak_points", text)

        if any(word in text for word in ["考试", "考研", "项目", "竞赛", "作业", "就业", "入门", "提升", "查漏补缺", "学懂", "掌握"]):
            set_fact("learning_goal", text)

        time_match = re.search(
            r"(\d+\s*(天|周|个月|小时|分钟)|一周|两周|半个月|一个月|半小时|一个半小时|两个小时|两小时)(内|左右|以内|以上|完成)?",
            text,
        )
        if time_match:
            set_fact("time_budget", time_match.group(0))

        if any(word in lower for word in ["视频", "图解", "动画", "代码", "实操", "练习", "题", "ppt", "markdown"]):
            formats = []
            for label, words in {
                "文字讲解": ["文字", "markdown"],
                "图解": ["图解", "图"],
                "视频/动画": ["视频", "动画"],
                "代码实验": ["代码", "实操", "实验"],
                "练习题": ["练习", "题"],
                "PPT": ["ppt", "PPT"],
            }.items():
                if label == "视频/动画" and any(negative in text for negative in ["不喜欢视频", "不要视频", "别给视频"]):
                    continue
                if any(word in text for word in words):
                    formats.append(label)
            set_fact("preference", "、".join(dict.fromkeys(formats)) or text)

    def merge_result_profile(self, state: ConversationState, result: dict[str, Any]) -> None:
        profile = result.get("profile", {})
        mapping = {
            "major": "background",
            "knowledge_base": "knowledge_base",
            "learning_goal": "learning_goal",
            "cognitive_style": "preference",
            "interests": "target_course",
        }
        for source_key, fact_key in mapping.items():
            item = profile.get(source_key)
            value = str(item.get("value", "")).strip() if isinstance(item, dict) else ""
            if value and value not in {"未知", "未提及", "暂无", "无"}:
                state.facts.setdefault(fact_key, value)

        weak_points = result.get("diagnosis", {}).get("weak_knowledge_points", [])
        if weak_points and "weak_points" not in state.facts:
            names = [str(point.get("name", "")) for point in weak_points if point.get("name")]
            if names:
                state.facts["weak_points"] = "、".join(names)

    # ── Read helpers (unchanged) ──────────────────────────────────────

    def missing_fields(self, state: ConversationState, limit: int | None = None) -> list[dict[str, str]]:
        missing = [
            {"key": key, "label": meta["label"], "question": meta["question"]}
            for key, meta in PROFILE_FIELD_DEFS.items()
            if not state.facts.get(key)
        ]
        return missing if limit is None else missing[:limit]

    def readiness(self, state: ConversationState) -> dict[str, Any]:
        filled = set(state.facts)
        missing_core = [key for key in CORE_FIELDS if key not in filled]
        ready_to_plan = PLAN_READY_FIELDS.issubset(filled)
        score = round(len(filled) / len(PROFILE_FIELD_DEFS), 2)
        return {
            "filledCount": len(filled),
            "totalCount": len(PROFILE_FIELD_DEFS),
            "score": score,
            "missingCore": missing_core,
            "readyToPlan": ready_to_plan,
        }

    def next_questions(self, state: ConversationState, limit: int = 2) -> list[str]:
        missing = self.missing_fields(state)
        priority = ["background", "target_course", "knowledge_base", "weak_points", "learning_goal", "time_budget", "preference"]
        ordered = sorted(missing, key=lambda item: priority.index(item["key"]) if item["key"] in priority else 99)
        return [item["question"] for item in ordered[:limit]]

    def known_lines(self, state: ConversationState) -> list[str]:
        lines = []
        for key, meta in PROFILE_FIELD_DEFS.items():
            value = state.facts.get(key)
            if value:
                lines.append(f"- {meta['label']}：{value}")
        return lines

    def supplemental_lines(self, state: ConversationState) -> list[str]:
        lines = []
        for key, meta in SUPPLEMENTAL_FIELD_DEFS.items():
            values = state.supplemental_facts.get(key, [])
            if values:
                lines.append(f"- {meta['label']}：{'、'.join(values)}")
        return lines

    def updated_lines(self, state: ConversationState) -> list[str]:
        return [
            f"- {PROFILE_FIELD_DEFS[key]['label']}：{state.facts[key]}"
            for key in state.last_updated_fields
            if key in PROFILE_FIELD_DEFS and key in state.facts
        ]

    def updated_supplemental_lines(self, state: ConversationState) -> list[str]:
        return [
            f"- {SUPPLEMENTAL_FIELD_DEFS[key]['label']}：{'、'.join(state.supplemental_facts[key])}"
            for key in state.last_updated_supplemental_fields
            if key in SUPPLEMENTAL_FIELD_DEFS and state.supplemental_facts.get(key)
        ]

    def profile_prompt(self, state: ConversationState, latest_message: str = "") -> str:
        known = "\n".join(self.known_lines(state)) or "- 暂无已记录画像"
        supplemental = "\n".join(self.supplemental_lines(state))
        if supplemental:
            known = f"{known}\n\n补充背景：\n{supplemental}"
        if latest_message:
            return f"用户最新输入：{latest_message}\n\n当前已记录学习画像：\n{known}"
        return f"当前已记录学习画像：\n{known}"

    # ── Internal helpers (unchanged) ──────────────────────────────────

    def _clean_fact_value(self, value: str) -> str:
        cleaned = value.strip(" ：:，。,.!?！？；;")
        cleaned = re.sub(r"^(一下|一下子|这个|这门|这方面)", "", cleaned).strip()
        cleaned = re.sub(r"^(用|在)?(一|两|二|三|四|五|六|七|八|九|十|\d+)(天|周|个月|小时|分钟)", "", cleaned).strip()
        if cleaned in {"什么", "啥", "这个", "这些", "信息", *COURSE_STOPWORDS}:
            return ""
        return cleaned

    def _clean_time_value(self, value: str) -> str:
        cleaned = value.strip(" ：:，。,.!?！？；;")
        return cleaned

    def _is_learning_background(self, value: str) -> bool:
        cleaned = self._clean_fact_value(value)
        if not cleaned:
            return False
        if cleaned in LOW_VALUE_BACKGROUND_WORDS:
            return False
        if len(cleaned) <= 2 and not any(hint in cleaned for hint in BACKGROUND_VALUE_HINTS):
            return False
        return any(hint in cleaned for hint in BACKGROUND_VALUE_HINTS)

    def _extract_knowledge_levels(self, text: str) -> tuple[list[str], list[str]]:
        strengths: list[str] = []
        weaknesses: list[str] = []

        segments = [segment.strip() for segment in re.split(r"[，。,.!?！？；;、]", text) if segment.strip()]
        for segment in segments:
            weak_match = re.search(r"(?:不会|不懂|没学过|没有学过|不太会|不熟)([A-Za-z+#一-鿿]{2,20})", segment)
            if weak_match:
                weaknesses.append(f"{weak_match.group(1)}：不会/不熟")
                continue

            front_weak_match = re.search(r"([A-Za-z+#一-鿿]{2,20})(?:比较|很|有点)?(?:薄弱|较弱|弱|差|一般|零基础)", segment)
            if front_weak_match:
                weaknesses.append(f"{front_weak_match.group(1)}：薄弱")
                continue

            strength_match = re.search(r"([A-Za-z+#一-鿿]{2,20}?)(?:还可以|可以|较好|不错|熟悉|会)", segment)
            if strength_match:
                topic = strength_match.group(1).rstrip("还也都很较比较")
                strengths.append(f"{topic}：{self._level_label(segment)}")

        return strengths, weaknesses

    def _level_label(self, segment: str) -> str:
        if any(word in segment for word in ["较好", "不错", "熟悉"]):
            return "较好"
        if "还可以" in segment or "可以" in segment:
            return "还可以"
        return "会"


# Module-level singleton — DB must be enabled via enable_db() at startup.
conversation_store = ConversationStore()
