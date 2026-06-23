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
from app.services.profile_extractor import GRADE_PATTERNS, MAJOR_ALIASES, extract_profile_facts
from app.utils.profile_normalizer import normalize_profile_dimensions


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
PLAN_READY_FIELDS = {"background", "target_course"}
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


def _estimated_path_days(stages: list[dict[str, Any]]) -> int:
    max_day = 0
    for stage in stages:
        duration = str(stage.get("duration", ""))
        for value in re.findall(r"\d+", duration):
            max_day = max(max_day, int(value))
    return max_day or 14


def _safe_estimated_days(raw_estimated: Any, stages: list[dict[str, Any]]) -> int:
    """Return *raw_estimated* if it is a positive integer, otherwise
    compute from *stages*.

    Guards against non-integer values (empty dicts, None, str, etc.) that
    can leak into the result when the planner agent fails.
    """
    if isinstance(raw_estimated, int) and raw_estimated > 0:
        return raw_estimated
    return _estimated_path_days(stages)


@dataclass
class ConversationState:
    session_id: str
    messages: list[dict[str, Any]] = field(default_factory=list)
    facts: dict[str, str] = field(default_factory=dict)
    supplemental_facts: dict[str, list[str]] = field(default_factory=dict)
    last_updated_fields: list[str] = field(default_factory=list)
    last_updated_supplemental_fields: list[str] = field(default_factory=list)
    last_conflicts: list[dict[str, str]] = field(default_factory=list)
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
                    # Normalize dimensions (handles old 8-dim and new 10-dim snapshots)
                    normalized_dims = normalize_profile_dimensions(profile.dimensions)
                    result["profile"] = {
                        dim.get("key", f"dim_{idx}"): {
                            "label": dim.get("label", ""),
                            "value": dim.get("value", ""),
                            "score": dim.get("score", 50),
                            "confidence": dim.get("confidence", 0.75),
                            "explanation": dim.get("explanation", dim.get("description", dim.get("value", ""))),
                            "evidence": dim.get("evidence", ""),
                            "source": dim.get("source", "rule_based_fallback"),
                        }
                        for idx, dim in enumerate(normalized_dims)
                    }
                    result["diagnosis"] = {"weak_knowledge_points": profile.weaknesses or []}
                    result["session_id"] = state.session_id
                    result["preferences"] = profile.preferences or {}
                if path:
                    result["learning_path"] = path.stages or []
                    result["course_id"] = path.course_id
                    result["course"] = {"course_id": path.course_id, "course_name": path.course_name}
                    # Restore recommended_strategy from path description
                    if path.description:
                        result.setdefault("diagnosis", {})
                        result["diagnosis"]["recommended_strategy"] = path.description
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
                            "related_stage_id": r.related_stage_id or "",
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

    # ── Public API ────────────────────────────────────────────────────

    _DEFAULT_SESSION = "frontend_session_001"

    def get(self, session_id: str | None) -> ConversationState:
        """Get or create the conversation state for *session_id*.

        Falls back to ``frontend_session_001`` when *session_id* is empty
        (backwards-compatible default for the single-user dev flow).
        """
        sid = (session_id or self._DEFAULT_SESSION).strip() or self._DEFAULT_SESSION
        if sid not in self._sessions:
            state = ConversationState(session_id=sid)
            self._sessions[sid] = state
            if self._db_enabled:
                self._hydrate_from_db(state)
        return self._sessions[sid]

    def get_state_or_none(self, session_id: str) -> ConversationState | None:
        """Return the state for *session_id* if it exists, otherwise *None*.

        Unlike ``get()``, this does **not** create a new state on demand.
        Use this when you want to check whether a session already has data
        without creating phantom sessions.
        """
        sid = session_id.strip()
        if not sid:
            return None
        if sid in self._sessions:
            return self._sessions[sid]
        if self._db_enabled:
            state = ConversationState(session_id=sid)
            self._sessions[sid] = state
            self._hydrate_from_db(state)
            # If hydration produced no data, treat as non-existent
            if not state.messages and not state.last_result:
                del self._sessions[sid]
                return None
            return state
        return None

    def reset(self, session_id: str | None) -> ConversationState:
        """Reset all state for a session (in-memory + DB)."""
        sid = (session_id or self._DEFAULT_SESSION).strip() or self._DEFAULT_SESSION
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
            db = None
            try:
                db = self._db_session()
                # Save profile snapshot
                profile_data = result.get("profile", {})
                dimensions_list = [
                    {
                        "key": key,
                        "label": item.get("label", key) if isinstance(item, dict) else key,
                        "value": str(item.get("value", "")) if isinstance(item, dict) else str(item),
                        "score": item.get("score", 50) if isinstance(item, dict) else 50,
                        "confidence": item.get("confidence", 0.75) if isinstance(item, dict) else 0.75,
                        "explanation": item.get("explanation", item.get("value", "")) if isinstance(item, dict) else str(item),
                        "evidence": item.get("evidence", "") if isinstance(item, dict) else "",
                        "source": item.get("source", "rule_based_fallback") if isinstance(item, dict) else "rule_based_fallback",
                    }
                    for key, item in profile_data.items()
                ]
                weaknesses_list = [
                    {"name": point.get("name", ""), "priority": point.get("priority", "medium")}
                    for point in result.get("diagnosis", {}).get("weak_knowledge_points", [])
                ]
                readiness = self.readiness(state)
                # Extract preferences from profile data or result
                prefs = result.get("preferences") or {}
                if not prefs:
                    # Build from conversation state facts as fallback
                    pref_fact = state.facts.get("preference", "")
                    if pref_fact:
                        prefs = {"preferredFormats": [pref_fact], "paceMinutes": 45, "difficulty": "beginner", "explainStyle": "diagram"}

                save_profile_snapshot(
                    db, state.session_id,
                    dimensions=dimensions_list,
                    weaknesses=weaknesses_list,
                    preferences=prefs if prefs else None,
                    readiness_score=readiness.get("score"),
                )

                # Save learning path if present
                if result.get("learning_path"):
                    stages = result.get("learning_path") or []
                    course_id = result.get("course_id", "") or state.session_id
                    path_data = {
                        "id": f"path_{state.session_id}_{course_id}",
                        "course_id": course_id,
                        "course_name": (result.get("course") or {}).get("course_name", ""),
                        "description": result.get("diagnosis", {}).get("recommended_strategy", ""),
                        "stages": stages,
                        "overallProgress": result.get("overallProgress", 0),
                        "estimatedDays": _safe_estimated_days(
                            result.get("estimatedDays"), stages
                        ),
                    }
                    save_learning_path(db, state.session_id, path_data)

                # Save resources if present — persist full structured data
                for item in result.get("resources", []):
                    raw_resource_id = str(item.get("resource_id", f"res_{time.time()}"))
                    resource_id = (
                        raw_resource_id
                        if raw_resource_id.startswith(f"{state.session_id}_")
                        else f"{state.session_id}_{raw_resource_id}"
                    )
                    # Determine format from content_format field
                    content_fmt = item.get("content_format", "markdown")
                    # Determine difficulty from item or default
                    difficulty = item.get("difficulty", "easy")
                    # Estimate minutes from content length
                    content_text = item.get("content", "")
                    estimated = max(10, len(content_text) // 200 * 5) if content_text else 20
                    related_points = list(item.get("related_knowledge_points") or [])
                    related_chapter = str(item.get("related_chapter") or "").strip()
                    if related_chapter:
                        related_points.append(related_chapter)
                    if item.get("related_stage_id"):
                        related_points.append(str(item.get("related_stage_id")))

                    save_resource(db, state.session_id, {
                        "id": resource_id,
                        "type": item.get("type", "lecture"),
                        "title": item.get("title", "学习资源"),
                        "description": item.get("description", ""),
                        "content": content_text,
                        "knowledge_points": list(dict.fromkeys(point for point in related_points if point)),
                        "tags": [content_fmt, item.get("source", "agent_generated"), item.get("quality_status", "")],
                        "difficulty": difficulty,
                        "estimated_minutes": estimated,
                        "format": "diagram" if content_fmt == "mermaid" else ("code" if item.get("type") == "practice" else "text"),
                        "mermaid_def": content_text if content_fmt == "mermaid" else None,
                        "code_blocks": item.get("code_blocks"),
                        "questions": item.get("items"),  # quiz items
                        "ppt_outline": item.get("ppt_outline"),
                        "bookmarked": item.get("bookmarked", False),
                        "study_status": item.get("study_status", "new"),
                        "source": item.get("source", "agent_generated"),
                        "related_stage_id": item.get("related_stage_id", ""),
                        "task_id": item.get("task_id", ""),
                    })
            except Exception:
                # Log but don't crash — in-memory state is already updated
                import logging
                logging.getLogger(__name__).exception(
                    "Failed to persist result to DB for session %s. In-memory state is preserved.",
                    session_id,
                )
            finally:
                if db is not None:
                    db.close()

    # ── Fact extraction (unchanged, pure processing logic) ─────────────

    def extract_facts(self, state: ConversationState, message: str) -> None:
        text = message.strip()
        state.last_updated_fields = []
        state.last_updated_supplemental_fields = []
        state.last_conflicts = []
        if not text:
            return

        lower = text.lower()

        def set_fact(key: str, value: str) -> None:
            cleaned = self._clean_time_value(value) if key == "time_budget" else self._clean_fact_value(value)
            if not cleaned:
                return
            old_value = state.facts.get(key, "")
            if old_value != cleaned:
                conflict_reason = self._fact_conflict_reason(key, old_value, cleaned)
                if conflict_reason:
                    state.last_conflicts.append(
                        {
                            "key": key,
                            "label": PROFILE_FIELD_DEFS.get(key, {}).get("label", key),
                            "old": old_value,
                            "new": cleaned,
                            "reason": conflict_reason,
                        }
                    )
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
            r"(?:想学习|想学|想系统学习|我要学|希望学|准备学|要学习|要学|入门|复习|掌握|了解)([^，。,.!?！？]{2,30})",
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

        _goal_words = {"考试", "考研", "项目", "竞赛", "作业", "就业", "入门", "提升", "查漏补缺", "学懂", "掌握"}
        if any(word in text for word in _goal_words):
            # Extract just the clause containing the goal marker, not the entire message
            segments = re.split(r"[，。,.!?！？；;]", text)
            goal_segment = ""
            for seg in segments:
                if any(word in seg for word in _goal_words):
                    goal_segment = seg.strip()
                    break
            set_fact("learning_goal", goal_segment or text)

        # Normalize Chinese single-digit numbers + time units to Arabic
        # so that "两天" → "2天", "一小时" → "1小时", etc.
        # Also strip measure-word "个" so "一个星期" → "1星期",
        # "两个小时" → "2小时".
        _cn_map = {"一": "1", "二": "2", "两": "2", "三": "3", "四": "4",
                   "五": "5", "六": "6", "七": "7", "八": "8", "九": "9"}
        time_text = re.sub(
            r"([一二两三四五六七八九])\s*个?\s*(天|周|个月|小时|分钟|星期)",
            lambda m: _cn_map[m.group(1)] + m.group(2),
            text,
        )

        time_match = re.search(
            r"(\d+\s*个?\s*(天|日|周|星期|个月|小时|分钟)|"
            r"[一二两三四五六七八九十半]+(?:个)?(?:天|星期)|"
            r"一周|两周|半个月|一个月|半小时|一个半小时|两个小时|两小时)"
            r"(内|左右|以内|以上|完成)?",
            time_text,
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

        extracted_profile_facts = extract_profile_facts(text)
        for key, value in extracted_profile_facts.facts.items():
            # Only fill gaps — never overwrite facts already set by the
            # regex patterns above (which use identity-context matching).
            if key not in state.facts or not state.facts[key]:
                set_fact(key, value)
        for key, values in extracted_profile_facts.supplemental.items():
            for value in values:
                add_supplemental(key, value)

    def merge_result_profile(self, state: ConversationState, result: dict[str, Any]) -> None:
        profile = result.get("profile", {})
        mapping = {
            "major_background": "background",
            "knowledge_base": "knowledge_base",
            "learning_goal": "learning_goal",
            "cognitive_style": "preference",
            "error_patterns": "weak_points",
            "coding_ability": "knowledge_base",
            "interest_direction": "target_course",
            "learning_rhythm": "time_budget",
            "self_efficacy": "preference",
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
        ready_to_plan = PLAN_READY_FIELDS.issubset(filled) and bool(
            state.facts.get("knowledge_base") or state.facts.get("learning_goal")
        )
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

    def conflict_lines(self, state: ConversationState) -> list[str]:
        return [
            f"- {item['label']}：已从「{item['old']}」更新为「{item['new']}」"
            for item in state.last_conflicts
            if item.get("old") and item.get("new")
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

    def _fact_conflict_reason(self, key: str, old_value: str, new_value: str) -> str:
        if not old_value or old_value == new_value:
            return ""
        if key == "background":
            old_grade, new_grade = self._matched_grade(old_value), self._matched_grade(new_value)
            old_major, new_major = self._matched_major(old_value), self._matched_major(new_value)
            if old_grade and new_grade and old_grade != new_grade:
                return "grade_changed"
            if old_major and new_major and old_major != new_major:
                return "major_changed"
            return ""
        if key in {"target_course", "time_budget"}:
            return f"{key}_changed"
        return ""

    def _matched_grade(self, value: str) -> str:
        return next((normalized for raw, normalized in GRADE_PATTERNS if raw in value or normalized in value), "")

    def _matched_major(self, value: str) -> str:
        return next((normalized for raw, normalized in MAJOR_ALIASES if raw in value or normalized in value), "")

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
