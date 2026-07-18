import json
import logging
import re
import threading
import time
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.orm import Session

from app.db.engine import SessionLocal
from app.db.repository import (
    delete_session,
    get_cross_session_learning_path,
    get_cross_session_resources,
    get_last_intent,
    get_latest_cross_session_profile,
    get_messages,
    get_or_create_session,
    save_message,
    save_profile_snapshot,
    upsert_daily_tasks,
    upsert_learning_path,
    upsert_resource,
    get_latest_profile,
    get_latest_learning_path,
    get_resources as repo_get_resources,
)
from app.utils.errors import MissingSessionIdError

logger = logging.getLogger(__name__)
from app.services.profile_extractor import GRADE_PATTERNS, MAJOR_ALIASES, extract_profile_facts
from app.utils.profile_normalizer import (
    normalize_profile_dimensions,
    detect_course_category,
    get_active_dimensions,
)


PROFILE_FIELD_DEFS: dict[str, dict[str, Any]] = {
    "background": {
        "label": "身份/专业背景",
        "question": "你现在的年级、专业或身份是什么？",
    },
    "learning_history": {
        "label": "学习历史",
        "question": "你之前学过哪些相关的课程或内容？成绩怎么样？有什么印象深刻的学习经历？",
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
PLAN_READY_FIELDS = {"background", "target_course", "knowledge_base", "learning_goal", "time_budget"}

# 浅层回答模式——这些值说明学生只是应付，没有给出有深度的信息
_SHALLOW_PATTERNS: tuple[str, ...] = (
    "学过一点", "了解一些", "还行", "还行吧", "一般", "一般般",
    "基础", "入门", "没学过", "零基础", "不知道", "不太清楚",
    "就那样", "差不多", "马马虎虎", "凑合", "还可以", "会一点",
    "懂一点", "接触过", "了解过", "大概", "基本",
)
_SHALLOW_MIN_LENGTH = 8  # 短于这个长度的回答几乎一定是浅层的

# 当某个维度已有浅层回答时，用追问来获取更深入的信息
_SHALLOW_FOLLOWUPS: dict[str, str] = {
    "background": "你具体是哪个学校、什么专业的？方便的话也可以说说年级～",
    "learning_history": "你之前学过的这些课程里，有没有哪门学得特别好或者特别吃力的？能举个例子吗？",
    "target_course": "你想学这门课是为了应对什么？考试、考研、还是做项目？想学到什么程度？",
    "knowledge_base": "你刚才说基础比较泛，能具体说说学过哪些内容、哪个部分觉得比较熟？",
    "weak_points": "能举个例子说说具体哪个题型或知识点觉得比较难吗？",
    "learning_goal": "你的目标具体是什么？比如通过期末考试、考研上岸、还是能独立做项目？",
    "time_budget": "每天大概能投入多长时间？是每天都能学还是只有周末？",
    "preference": "你更喜欢看文本文档、看视频、做练习题、还是画思维导图？",
}
LOW_VALUE_BACKGROUND_WORDS = {
    "男生", "女生", "男", "女", "男孩子", "女孩子", "普通人", "学生", "大学生",
}
# 常见中文姓氏——用于判断提取的内容是否像人名而非学习背景
_COMMON_SURNAMES = set("王李张刘陈杨黄赵周吴徐孙马胡朱郭何罗高林郑梁谢宋唐许邓冯韩曹曾彭萧蔡潘田董袁于余叶蒋杜苏魏吕丁任卢姚钟姜崔谭廖范汪陆金石戴贾韦夏付方白邹孟熊秦邱江尹薛闫段雷侯龙史陶黎贺顾毛郝龚邵万钱严覃武莫孔向汤温康施文牛樊葛邢安齐易乔伍庞余".replace(" ", ""))
BACKGROUND_VALUE_HINTS = {
    "专业", "工程", "计算机", "软件", "人工智能", "电子", "信息", "自动化",
    "数学", "统计", "大一", "大二", "大三", "大四", "研究生", "本科", "高职", "课程",
}
COURSE_STOPWORDS = {
    "方案", "学习方案", "路径", "学习路径", "计划", "学习计划",
    "复习", "入门", "掌握", "高分", "期末", "考试", "目标", "核心题型", "开始",
}
COURSE_KEYWORDS = (
    "微积分", "高等数学", "线性代数", "数据结构", "机器学习", "人工智能导论",
    "人工智能", "深度学习", "操作系统", "计算机网络", "Python", "python",
    "考研英语",
)


def _estimated_path_days(stages: list[dict[str, Any]]) -> int:
    max_day = 0
    for stage in stages:
        duration = str(stage.get("duration", ""))
        for value in re.findall(r"\d+", duration):
            max_day = max(max_day, int(value))
    return max_day or 14


def _safe_estimated_days(raw_estimated: Any, stages: list[dict[str, Any]]) -> int:
    if isinstance(raw_estimated, int) and raw_estimated > 0:
        return raw_estimated
    return _estimated_path_days(stages)


def _find_new_stages(old_stages: list, new_stages: list) -> list[dict]:
    """找出新增的 stage（在 new 中有但 old 中没有的 stage_id）。"""
    old_ids = {s.get("stage_id", "") for s in old_stages if isinstance(s, dict)}
    return [s for s in new_stages if isinstance(s, dict) and s.get("stage_id", "") not in old_ids]


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
    last_image_input: dict[str, Any] | None = None
    last_uploaded_file: dict[str, Any] | None = None
    last_vision_result: dict[str, Any] | None = None
    last_extracted_questions: list[dict[str, Any]] = field(default_factory=list)
    last_multimodal_task_context: dict[str, Any] = field(default_factory=dict)
    last_proposal: str | None = None  # 上一轮向用户确认了什么：plan/resources/questions/full/None
    feedback_signal: Any | None = None  # FeedbackSignal from grading → next request (replaces _pending_adjustment)
    generating: bool = False
    current_progress: dict[str, Any] | None = None
    updated_at: float = field(default_factory=time.time)
    # 标记核心 facts 是否有更新，用于触发画像维度增量重建
    profile_dirty: bool = False
    # 是否启用对话文字自动画像提取（默认关闭，仅在路径规划专用对话中开启）
    profile_extraction_enabled: bool = True
    path_planning_info_mode: bool = False  # 路径规划信息收集模式（不触发Planner）
    pending_revision: dict | None = None  # 待用户确认的路径调整候选
    path_revisions: list[dict] = field(default_factory=list)  # 历史版本快照
    # 结构化画像（topic 级明细、置信度、证据链）
    rich_facts: dict[str, Any] = field(default_factory=lambda: {
        dim: {"summary": "", "topics": [], "gaps_found": [], "probe_history": [], "next_probe_topics": [], "last_probed_at": 0}
        for dim in ("background", "target_course", "knowledge_base", "weak_points", "learning_goal", "time_budget", "preference")
    })


# 核心画像事实字段——这些字段更新时会触发画像维度重建
_PROFILE_CORE_FIELDS = frozenset({
    "background", "target_course", "knowledge_base",
    "weak_points", "learning_goal", "time_budget", "preference",
})


class ConversationStore:
    """Session state manager with in-memory cache and DB persistence."""

    def __init__(self) -> None:
        self._sessions: dict[str, ConversationState] = {}
        self._db_enabled: bool = False
        self._lock = threading.Lock()

    def enable_db(self) -> None:
        self._db_enabled = True

    def _db_session(self) -> Session:
        return SessionLocal()

    def _hydrate_from_db(self, state: ConversationState) -> None:
        try:
            db = self._db_session()
            db_messages = get_messages(db, state.session_id)
            state.messages = [
                {
                    "role": m.role,
                    "content": m.content,
                    "timestamp": int(m.created_at.timestamp() * 1000) if m.created_at else int(time.time() * 1000),
                }
                for m in db_messages
            ]
            state.last_intent = get_last_intent(db, state.session_id)
            profile = get_latest_cross_session_profile(db, state.session_id)
            path = get_cross_session_learning_path(db, state.session_id)
            db_resources = get_cross_session_resources(db, state.session_id)
            if profile or path or db_resources:
                result: dict[str, Any] = {}
                if profile:
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
                    if path.description:
                        result.setdefault("diagnosis", {})
                        result["diagnosis"]["recommended_strategy"] = path.description
                if db_resources:
                    result["resources"] = [
                        {
                            "resource_id": r.id, "type": r.type, "title": r.title,
                            "description": r.description or "", "content": r.content or "",
                            "content_format": "markdown", "source": "db",
                            "related_stage_id": r.related_stage_id or "",
                        }
                        for r in db_resources
                    ]
                state.last_result = result if result else None
            state.facts.clear()
            state.supplemental_facts.clear()
            for msg in state.messages:
                if msg.get("role") == "user":
                    self.extract_facts(state, str(msg.get("content", "")))
            # Populate missing facts from cross-session profile
            if profile and profile.dimensions:
                _dim_to_fact = {
                    "major_background": "background",
                    "knowledge_base": "knowledge_base",
                    "learning_goal": "learning_goal",
                    "cognitive_style": "preference",
                    "error_patterns": "weak_points",
                    "coding_ability": "knowledge_base",
                    "interest_direction": "target_course",
                    "learning_rhythm": "time_budget",
                }
                for dim in profile.dimensions:
                    dim_key = dim.get("key", "") if isinstance(dim, dict) else ""
                    fact_key = _dim_to_fact.get(dim_key, dim_key)
                    if fact_key in PROFILE_FIELD_DEFS and fact_key not in state.facts:
                        val = str(dim.get("value", "")).strip() if isinstance(dim, dict) else ""
                        if val and val not in ("未知", "未提及", "暂无", "无", ""):
                            state.facts[fact_key] = val
        finally:
            db.close()

    @staticmethod
    def _require_session_id(session_id: str | None) -> str:
        sid = str(session_id or "").strip()
        if not sid:
            raise MissingSessionIdError()
        return sid

    def get(self, session_id: str | None) -> ConversationState:
        sid = self._require_session_id(session_id)
        with self._lock:
            if sid not in self._sessions:
                state = ConversationState(session_id=sid)
                self._sessions[sid] = state
                if self._db_enabled:
                    self._hydrate_from_db(state)
            return self._sessions[sid]

    def get_state_or_none(self, session_id: str) -> ConversationState | None:
        sid = str(session_id or "").strip()
        if not sid:
            return None
        if sid in self._sessions:
            return self._sessions[sid]
        if self._db_enabled:
            state = ConversationState(session_id=sid)
            self._sessions[sid] = state
            self._hydrate_from_db(state)
            if not state.messages and not state.last_result:
                del self._sessions[sid]
                return None
            return state
        return None

    def reset(self, session_id: str | None) -> ConversationState:
        sid = self._require_session_id(session_id)
        self._sessions[sid] = ConversationState(session_id=sid)
        if self._db_enabled:
            try:
                db = self._db_session()
                delete_session(db, sid)
                get_or_create_session(db, sid)
            finally:
                db.close()
        return self._sessions[sid]

    def append_message(self, session_id: str | None, role: str, content: str) -> ConversationState:
        state = self.get(session_id)
        state.messages.append({
            "role": role, "content": content,
            "timestamp": int(time.time() * 1000),
        })
        state.updated_at = time.time()
        if role == "user":
            self.extract_facts_with_llm(state, content)
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

    def set_proposal(self, session_id: str | None, proposal: str | None) -> None:
        """记录上一轮向用户确认了什么：plan/resources/questions/full/None"""
        state = self.get(session_id)
        state.last_proposal = proposal
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
                prefs = dict(result.get("preferences") or {})
                if isinstance(result.get("profile_v2"), dict):
                    prefs["profile_v2"] = result["profile_v2"]
                if not prefs:
                    pref_fact = state.facts.get("preference", "")
                    if pref_fact:
                        prefs = {"preferredFormats": [pref_fact], "paceMinutes": 45, "difficulty": "beginner", "explainStyle": "diagram"}
                save_profile_snapshot(db, state.session_id, dimensions=dimensions_list, weaknesses=weaknesses_list, preferences=prefs if prefs else None, readiness_score=readiness.get("score"))
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
                        "estimatedDays": _safe_estimated_days(result.get("estimatedDays"), stages),
                    }
                    upsert_learning_path(db, state.session_id, path_data)
                    # Derive and persist daily tasks from stage data
                    if stages:
                        daily_tasks_list = self._derive_daily_tasks_from_stages(
                            state.session_id, stages
                        )
                        if daily_tasks_list:
                            upsert_daily_tasks(db, state.session_id, daily_tasks_list)
                # ── 资源持久化 ──
                try:
                    for item in result.get("resources", []):
                        raw_resource_id = str(item.get("resource_id", f"res_{time.time()}"))
                        resource_id = raw_resource_id if raw_resource_id.startswith(f"{state.session_id}_") else f"{state.session_id}_{raw_resource_id}"
                        content_fmt = item.get("content_format") or item.get("format", "markdown")
                        difficulty = item.get("difficulty", "easy")
                        content_text = item.get("content", "")
                        estimated = max(10, len(content_text) // 200 * 5) if content_text else 20
                        related_points = list(item.get("related_knowledge_points") or [])
                        related_chapter = str(item.get("related_chapter") or "").strip()
                        if related_chapter:
                            related_points.append(related_chapter)
                        if item.get("related_stage_id"):
                            related_points.append(str(item.get("related_stage_id")))
                        upsert_resource(db, state.session_id, {
                            "id": resource_id, "type": item.get("type", "lecture"),
                            "title": item.get("title", "学习资源"), "description": item.get("description", ""),
                            "content": content_text,
                            "knowledge_points": list(dict.fromkeys(point for point in related_points if point)),
                            "tags": [content_fmt, item.get("source", "agent_generated"), item.get("quality_status", "")],
                            "difficulty": difficulty, "estimated_minutes": estimated,
                            "format": "diagram" if content_fmt == "mermaid" else ("code" if item.get("type") == "practice" else "text"),
                            "mermaid_def": content_text if content_fmt == "mermaid" else None,
                            "code_blocks": item.get("code_blocks"), "questions": item.get("items"),
                            "ppt_outline": item.get("ppt_outline"),
                            "bookmarked": item.get("bookmarked", False),
                            "study_status": item.get("study_status", "new"),
                            "source": item.get("source", "agent_generated"),
                            "related_stage_id": item.get("related_stage_id", ""),
                            "task_id": item.get("task_id", ""),
                        })
                except Exception:
                    import logging as _logging
                    _logging.getLogger(__name__).exception("Failed to persist resources to DB for session %s.", session_id)

                # ── 题目持久化 ──
                try:
                    questions = result.get("questions", [])
                    if questions:
                        qsid = result.get("question_set_id", f"qs_{state.session_id}")
                        from app.db.repository import upsert_questions as repo_upsert_questions
                        for q in questions:
                            if isinstance(q, dict) and not q.get("question_set_id"):
                                q["question_set_id"] = qsid
                        repo_upsert_questions(db, state.session_id, questions)
                except Exception:
                    import logging as _logging
                    _logging.getLogger(__name__).exception("Failed to persist questions to DB for session %s.", session_id)
            except Exception:
                import logging as _logging
                _logging.getLogger(__name__).exception("Failed to persist result to DB for session %s.", session_id)
            finally:
                if db is not None:
                    db.close()

    def get_multimodal_context(self, session_id: str | None) -> dict[str, Any]:
        state = self.get(session_id)
        return {
            "last_image_input": state.last_image_input,
            "last_uploaded_file": state.last_uploaded_file,
            "last_vision_result": state.last_vision_result,
            "last_extracted_questions": list(state.last_extracted_questions or []),
            "last_multimodal_task_context": dict(state.last_multimodal_task_context or {}),
        }

    def set_multimodal_context(self, session_id: str | None, context: dict[str, Any]) -> None:
        state = self.get(session_id)
        if isinstance(context.get("last_image_input"), dict):
            state.last_image_input = context["last_image_input"]
        if isinstance(context.get("last_uploaded_file"), dict):
            state.last_uploaded_file = context["last_uploaded_file"]
        if isinstance(context.get("last_vision_result"), dict):
            state.last_vision_result = context["last_vision_result"]
        if isinstance(context.get("last_extracted_questions"), list):
            state.last_extracted_questions = [
                item for item in context["last_extracted_questions"] if isinstance(item, dict)
            ]
        if isinstance(context.get("last_multimodal_task_context"), dict):
            state.last_multimodal_task_context = context["last_multimodal_task_context"]
        state.updated_at = time.time()

    def _derive_daily_tasks_from_stages(
        self,
        session_id: str,
        stages: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Flatten per-stage daily_tasks into flat records for the daily_tasks table.

        Handles both LLM-generated daily_tasks (per-day breakdown) and
        fallback data.  Each item in the returned list is a dict suitable
        for upsert_daily_tasks().
        """
        result: list[dict[str, Any]] = []

        for stage in stages:
            if not isinstance(stage, dict):
                continue

            stage_id = stage.get("stage_id", "")
            duration = str(stage.get("duration", "第1天"))
            daily_tasks_raw = stage.get("daily_tasks")
            stage_tasks = stage.get("tasks", [])
            if not isinstance(stage_tasks, list):
                stage_tasks = []
            source = stage.get("source", "rule_fallback")

            # Parse day range from duration like "第1-3天"
            day_nums = re.findall(r"\d+", duration)
            if len(day_nums) >= 2:
                start_day, end_day = int(day_nums[0]), int(day_nums[1])
            elif len(day_nums) == 1:
                start_day = end_day = int(day_nums[0])
            else:
                start_day = end_day = 1

            if daily_tasks_raw and isinstance(daily_tasks_raw, list):
                # Use LLM-derived or fallback-derived daily breakdown
                for entry in daily_tasks_raw:
                    if not isinstance(entry, dict):
                        continue
                    day = int(entry.get("day", start_day))
                    titles = entry.get("tasks", [])
                    if isinstance(titles, list):
                        for t in titles:
                            title = str(t).strip()
                            if title:
                                result.append({
                                    "session_id": session_id,
                                    "stage_id": stage_id,
                                    "day_index": day,
                                    "day_label": f"第{day}天",
                                    "title": title,
                                    "source": source,
                                })
            else:
                # Last-resort: distribute stage tasks across the stage's day range
                num_days = max(1, end_day - start_day + 1)
                if not stage_tasks:
                    stage_tasks = ["学习课程讲义", "完成配套练习"]

                for idx, task_text in enumerate(stage_tasks):
                    title = str(task_text).strip()
                    if not title:
                        continue
                    day = start_day + (idx % num_days)
                    result.append({
                        "session_id": session_id,
                        "stage_id": stage_id,
                        "day_index": day,
                        "day_label": f"第{day}天",
                        "title": title,
                        "source": source,
                    })

        return result

    def set_diagnosis(self, session_id: str, diagnosis: dict[str, Any]) -> None:
        state = self.get(session_id)
        result = dict(state.last_result or {})
        result.setdefault("session_id", state.session_id)
        result["diagnosis"] = diagnosis
        state.last_result = result
        state.updated_at = time.time()

    # ── 路径版本管理 ─────────────────────────────────────────────

    def set_pending_revision(
        self,
        session_id: str,
        proposed_stages: list[dict],
        diff: dict,
        reason: str = "",
        path_id: str = "",
        subject_id: str = "",
        trigger_source: str = "",
        trigger_id: str = "",
    ) -> dict:
        """存储候选路径供用户确认，不覆盖当前 active path。"""
        state = self.get(session_id)
        if state.pending_revision:
            return state.pending_revision
        revision = {
            "revision_id": f"rev_{int(time.time() * 1000)}",
            "created_at": time.time(),
            "status": "ready_for_review",
            "reason": reason,
            "summary": diff.get("summary", ""),
            "diff": diff,
            "proposed_stages": proposed_stages,
            "diagnosis_snapshot_id": f"diag_{int(time.time() * 1000)}",
            "path_id": path_id,
            "subject_id": subject_id,
            "trigger_source": trigger_source,
            "trigger_id": trigger_id,
        }
        state.pending_revision = revision
        state.updated_at = time.time()
        # 持久化到 DB
        if self._db_enabled:
            try:
                db = self._db_session()
                from app.db.models import LearningPathModel
                from app.db.repository import get_or_create_session
                get_or_create_session(db, session_id)
                existing = (
                    db.query(LearningPathModel)
                    .filter(LearningPathModel.session_id == session_id)
                    .order_by(LearningPathModel.updated_at.desc())
                    .first()
                )
                if existing:
                    revision["path_id"] = revision["path_id"] or existing.id
                    revision["subject_id"] = revision["subject_id"] or str(getattr(existing.session, "subject_id", "") or "")
                if existing:
                    existing.pending_revision = revision
                else:
                    lr = state.last_result or {}
                    db.add(LearningPathModel(
                        id=f"path_{session_id}",
                        session_id=session_id,
                        pending_revision=revision,
                        stages=lr.get("learning_path", []),
                    ))
                db.commit()
                import logging
                logger = logging.getLogger(__name__)
                logger.info("set_pending_revision persisted for session=%s", session_id)
            except Exception as exc:
                import logging
                logging.getLogger(__name__).warning("set_pending_revision DB failed: %s", exc)
            finally:
                db.close()
        return revision

    def apply_pending_revision(self, session_id: str) -> dict | None:
        """用户确认候选路径，将 proposed_stages 写入 active path。"""
        state = self.get(session_id)
        if not state.pending_revision:
            # DB 兜底
            self.get_pending_revision(session_id)
        if not state.pending_revision:
            return None
        rev = state.pending_revision
        # 当前路径入历史
        current = dict(state.last_result or {})
        old_path = current.get("learning_path", [])
        if old_path:
            snapshot = {
                "version": len(state.path_revisions) + 1,
                "stages": old_path,
                "applied_at": time.time(),
                "reason": "被新版本替换",
            }
            state.path_revisions.append(snapshot)
        # 应用候选路径
        rev["status"] = "applied"
        rev["decided_at"] = time.time()
        current["learning_path"] = rev["proposed_stages"]
        current["version"] = int(time.time() * 1000)
        state.last_result = current
        state.pending_revision = None
        state.updated_at = time.time()
        # 持久化到 DB
        if self._db_enabled:
            try:
                db = self._db_session()
                from app.db.models import LearningPathModel
                existing = (
                    db.query(LearningPathModel)
                    .filter(LearningPathModel.session_id == session_id)
                    .order_by(LearningPathModel.updated_at.desc())
                    .first()
                )
                if existing:
                    existing.pending_revision = None
                    existing.path_revisions = state.path_revisions
                    existing.stages = rev["proposed_stages"]
                    existing.current_version = len(state.path_revisions)
                    db.commit()
            except Exception:
                pass
            finally:
                db.close()
        return {"success": True, "version": current["version"],
                "_new_stages": _find_new_stages(old_path, rev["proposed_stages"])}

    def reject_pending_revision(self, session_id: str) -> None:
        """用户拒绝候选路径。"""
        state = self.get(session_id)
        if state.pending_revision:
            state.pending_revision["status"] = "rejected"
            state.pending_revision["decided_at"] = time.time()
            state.pending_revision = None
            state.updated_at = time.time()
            if self._db_enabled:
                db = None
                try:
                    db = self._db_session()
                    from app.db.models import LearningPathModel
                    path = (
                        db.query(LearningPathModel)
                        .filter(LearningPathModel.session_id == session_id)
                        .order_by(LearningPathModel.updated_at.desc())
                        .first()
                    )
                    if path:
                        path.pending_revision = None
                        db.commit()
                finally:
                    if db is not None:
                        db.close()

    def get_pending_revision(self, session_id: str) -> dict | None:
        """获取待确认的候选路径（内存优先，DB 兜底）。"""
        state = self.get(session_id)
        if state.pending_revision:
            return state.pending_revision
        # DB 兜底：其他进程写入的 pending_revision
        if self._db_enabled:
            try:
                db = self._db_session()
                from app.db.models import LearningPathModel
                existing = db.get(LearningPathModel, f"path_{session_id}")
                if existing and existing.pending_revision:
                    state.pending_revision = existing.pending_revision
                    return existing.pending_revision
            except Exception as exc:
                import logging
                logging.getLogger(__name__).warning("get_pending_revision DB fallback failed: %s", exc)
            finally:
                db.close()
        return None

    # ── 结构化画像（topic 级别）──

    def set_rich_fact_topic(
        self, state: ConversationState, dim: str, topic: str,
        *, level: str = "", detail: str = "", confidence: float = 0.5,
        evidence: str = "", source_text: str = "", verified_by: str = "",
    ) -> None:
        """更新结构化画像中的单个 topic。"""
        rich = state.rich_facts.setdefault(dim, {"summary": "", "topics": [], "gaps_found": [], "probe_history": [], "next_probe_topics": [], "last_probed_at": 0})
        existing = [t for t in rich.get("topics", []) if t.get("topic") == topic]
        now = time.time()
        if existing:
            t = existing[0]
            if detail:
                t["detail"] = detail
            if level:
                t["level"] = level
            if evidence:
                # 不覆盖已有 evidence，追加
                t.setdefault("evidence_history", []).append(t.get("evidence", ""))
                t["evidence"] = evidence
            if source_text:
                t["source_text"] = source_text
            if verified_by:
                t["verified_by"] = verified_by
            t["confidence"] = max(t.get("confidence", 0), confidence)
            t["updated_at"] = now
        else:
            rich["topics"].append({
                "topic": topic, "level": level or "unknown",
                "detail": detail or "", "confidence": confidence,
                "evidence": evidence or "", "source_text": source_text or "",
                "verified_by": verified_by or "", "created_at": now, "updated_at": now,
            })
        rich["last_probed_at"] = now

    def get_rich_fact_topics(self, state: ConversationState, dim: str) -> list[dict]:
        """获取结构化画像中的 topic 列表。"""
        rich = state.rich_facts.get(dim, {})
        return rich.get("topics", [])

    def add_probe_history(self, state: ConversationState, dim: str, probe: str) -> None:
        """记录对该维度的探针历史。"""
        rich = state.rich_facts.setdefault(dim, {"summary": "", "topics": [], "gaps_found": [], "probe_history": [], "next_probe_topics": [], "last_probed_at": 0})
        history = rich.setdefault("probe_history", [])
        if probe not in history:
            history.append(probe)

    def set_next_probe_topics(self, state: ConversationState, dim: str, topics: list[str]) -> None:
        """设置接下来应追问的 topic 列表。"""
        rich = state.rich_facts.setdefault(dim, {"summary": "", "topics": [], "gaps_found": [], "probe_history": [], "next_probe_topics": [], "last_probed_at": 0})
        rich["next_probe_topics"] = topics

    def extract_facts_with_llm(self, state: ConversationState, message: str) -> None:
        """用 LLM 从用户消息中提取画像事实。如果 LLM 不可用，回退到正则提取。"""
        state.last_updated_fields = []
        state.last_updated_supplemental_fields = []
        state.last_conflicts = []

        if not message.strip():
            return

        try:
            from app.services.llm_client import get_llm_client
            from app.config import settings
            llm = get_llm_client(settings.llm_provider)
        except Exception:
            self.extract_facts(state, message)
            return

        known_facts = "\n".join(
            f"- {PROFILE_FIELD_DEFS[k]['label']}：{v}"
            for k, v in state.facts.items() if v and k in PROFILE_FIELD_DEFS
        ) or "- 暂无已记录信息"

        history_text = "\n".join(
            f"- {m['role']}: {m['content'][:200]}"
            for m in state.messages[-6:]
        )

        # ── Detect probing patterns in recent history ──
        # When DeepTutor used indirect probing last turn (diagnostic questions,
        # concept explanations, preference choices, scenario tests), extract
        # what the student's response reveals about their real profile.
        _probe_context = ""
        _prev_assistant = ""
        for m in reversed(state.messages[-4:]):
            if m.get("role") == "assistant":
                _prev_assistant = str(m.get("content", ""))
                break

        # Detect probe type from previous assistant message
        _probe_type = ""
        _diagnostic_markers = ["考你一下", "你觉得对吗", "下面哪个", "正确的是", "以下哪个", "判断", "测测", "摸底"]
        _concept_markers = ["你能解释", "说说看", "用自己的话", "什么是", "的区别是"]
        _preference_markers = ["文字解释还是", "画个图", "哪种方式", "你喜欢"]
        _scenario_markers = ["如果", "你会怎么", "遇到", "试试看"]
        _goal_markers = ["最想做到", "学完", "能自己", "目标"]
        _time_markers = ["整块还是", "碎片", "周末也", "最少能"]

        if any(m in _prev_assistant for m in _diagnostic_markers):
            _probe_type = "diagnostic_quiz"
        elif any(m in _prev_assistant for m in _concept_markers):
            _probe_type = "concept_explanation"
        elif any(m in _prev_assistant for m in _preference_markers):
            _probe_type = "preference_choice"
        elif any(m in _prev_assistant for m in _scenario_markers):
            _probe_type = "scenario_test"
        elif any(m in _prev_assistant for m in _goal_markers):
            _probe_type = "goal_probe"
        elif any(m in _prev_assistant for m in _time_markers):
            _probe_type = "time_reality_check"

        if _probe_type:
            _probe_hints = {
                "diagnostic_quiz": (
                    "上一轮出了一道诊断题来探测学生的真实知识水平.根据学生回答的对错和解释质量:\n"
                    "- 答对且解释清楚 -> 提取 knowledge_base 为具体的掌握描述,如[探测]能正确判断XXX\n"
                    "- 答错或回避 -> 提取 weak_points 为暴露出的具体薄弱点,如[探测]对YYY理解有误\n"
                ),
                "concept_explanation": (
                    "上一轮让学生解释了一个概念.根据解释的准确性和深度:\n"
                    "- 解释清晰准确 -> 提取 knowledge_base 为具体掌握程度\n"
                    "- 解释模糊或错误 -> 提取 weak_points 为概念混淆的具体点\n"
                ),
                "preference_choice": (
                    "上一轮给了学生一个学习方式的自然选择(文字vs图解等).从学生的选择中提取 preference.\n"
                ),
                "scenario_test": (
                    "上一轮用场景题探测了学生的应对能力.从回答中提取 knowledge_base 或 weak_points.\n"
                ),
                "goal_probe": (
                    "上一轮深入探测了学习目标的真实动机和具体程度.提取 learning_goal 为有深度的描述.\n"
                ),
                "time_reality_check": (
                    "上一轮确认了时间安排的真实性(区分理想vs实际).提取 time_budget 为更精确的描述.\n"
                ),
            }
            _probe_context = (
                "\n## 探测结果提取模式\n"
                + _probe_hints.get(_probe_type, "上一轮进行了画像探测,从学生回答中提取有深度的画像信息.\n")
                + "- 提取的值必须带上 evidence(如[探测][学生自述][行为观察])\n"
                "- 值要具体,避免笼统描述\n"
            )

        # ── Detect course type for mode-specific extraction ──
        # Check BOTH stored facts AND current message (covers first message before facts are stored)
        target = str(state.facts.get("target_course", "")).strip()
        msg_lower = message.lower()
        lang_kw = ["英语","日语","韩语","法语","德语","西语","语言","雅思","托福","gre","toefl","ielts","英文","日文"]
        prog_kw = ["python","java","c++","编程","前端","后端","开发","代码","写一个","搭建"]
        is_language = any(w in target for w in lang_kw) or any(w in msg_lower for w in lang_kw)
        is_programming = any(w in target for w in prog_kw) or any(w in msg_lower for w in prog_kw)

        extra_dims = ""
        extra_rules = ""
        if is_language:
            extra_dims = (
                "- current_level: 当前语言水平（如：零基础/初级/中级/高级、CET4/CET6/专八、雅思6.5等）\n"
                "- target_score: 目标分数或等级\n"
                "- weak_skill: 薄弱技能（听力/阅读/写作/口语/词汇/语法中哪项最弱）\n"
                "- daily_vocab_goal: 每日背词量目标\n"
            )
            extra_rules = "8. 语言类课程：水平描述要具体(如CET4 425分)，不要只说'一般'\n"
        elif is_programming:
            extra_dims = (
                "- coding_level: 编程水平（零基础/学过语法/能写小项目/熟练）\n"
                "- preferred_language: 偏好的编程语言\n"
                "- project_goal: 想做什麼项目或方向\n"
            )
            extra_rules = "8. 编程类课程：区分'学过语法不会用'和'能独立开发'\n"

        prompt = (
            "你是一个学习画像提取器。从用户消息中提取以下维度的信息。\n\n"
            "## 已有画像\n" + known_facts + "\n\n"
            "## 对话历史(最近几轮)\n" + history_text + "\n\n"
            + _probe_context +
            "\n## 用户最新消息\n" + message + "\n\n"
            "## 需要提取的维度\n"
            "- background: 身份/专业背景（只提取专业、年级、学校等学习相关信息，严禁提取人名、昵称、称呼）\n"
            "- target_course: 目标课程/知识方向\n"
            "- knowledge_base: 已有基础\n"
            "- weak_points: 薄弱点\n"
            "- learning_goal: 学习目标\n"
            "- time_budget: 时间安排\n"
            "- preference: 学习偏好\n" +
            extra_dims + "\n"
            "## 规则\n"
            "1. 只提取用户明确提到的信息,不要推测\n"
            "2. 课程名要完整准确,如微积分、数据结构、Python\n"
            "3. 零基础是基础水平,完全只是程度副词\n"
            "4. 疑问句中的'是什么'、'的是什么'、'这个'绝对不要提取为课程名\n"
            "5. 如果用户只是在提问没说出具体课程,target_course留空\n"
            "6. 绝对不要提取人名、昵称、称呼（如'小明''张三'等）到 background 或任何字段\n"
            "7. 只返回JSON: {\"updates\": {...}, \"conflicts\": []}\n" +
            extra_rules
        )

        try:
            raw = llm.chat(
                messages=[
                    {"role": "system", "content": "你是精准的信息提取器。只返回JSON。"},
                    {"role": "user", "content": prompt},
                ],
                temperature=0,
                max_tokens=500,
            )
            cleaned = raw.strip()
            if cleaned.startswith("```"):
                cleaned = cleaned.split("\n", 1)[1]
                if cleaned.endswith("```"):
                    cleaned = cleaned[:-3]
            result = json.loads(cleaned.strip())
            updates = result.get("updates", {})
        except Exception:
            self.extract_facts(state, message)
            return

        key_mapping = {
            "background": "background",
            "target_course": "target_course",
            "knowledge_base": "knowledge_base",
            "weak_points": "weak_points",
            "learning_goal": "learning_goal",
            "time_budget": "time_budget",
            "preference": "preference",
        }

        invalid_values = {
            "的是什么", "的是什么诶", "什么", "啥", "这个", "那个",
            "它", "他", "她", "未知", "未提及", "无", "none", "null", "完全", ""
        }

        for llm_key, fact_key in key_mapping.items():
            value = str(updates.get(llm_key, "")).strip()
            if not value or value in invalid_values or len(value) <= 1:
                continue
            self._set_fact(state, fact_key, value, source_text=message)

        if not state.last_updated_fields:
            self.extract_facts(state, message)

    def extract_facts(self, state: ConversationState, message: str) -> None:
        text = message.strip()
        state.last_updated_fields = []
        state.last_updated_supplemental_fields = []
        state.last_conflicts = []
        if not text:
            return

        lower = text.lower()

        # A request explicitly scoped to this turn is a presentation constraint,
        # not a durable learner fact.
        if any(marker in text for marker in ("这次", "本次", "当前")) and any(
            marker in text for marker in ("简单", "简要", "概览", "了解一下")
        ):
            return

        def set_fact(key: str, value: str, *, force: bool = False) -> None:
            self._set_fact(state, key, value, source_text=text, force=force)

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
                elif not self._looks_like_name_intro(background_value):
                    add_supplemental("personal_background", background_value)
                break

        if "运动员" in text:
            add_supplemental("identity_note", "运动员")

        if any(word in text for word in ["感兴趣", "喜欢", "想做", "方向"]):
            interest_match = re.search(r"(?:对|喜欢|想做)([^，。,.!?！？]{2,30})(?:感兴趣|方向|项目)?", text)
            if interest_match and "学习" not in interest_match.group(1):
                add_supplemental("interest_note", interest_match.group(1))

        course_override = self._explicit_course_override(text)
        if course_override:
            set_fact("target_course", course_override, force=True)
        else:
            known_course = self._known_course_from_text(text)
            if known_course and any(word in text for word in ["想", "学", "学习", "复习", "准备", "考研", "入门", "掌握"]):
                set_fact("target_course", known_course)

            course_match = re.search(
                r"(?:想学习|想学|想系统学习|我要学|希望学|准备学|要学习|要学|准备考)([^，。,.!?！？]{2,30})",
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

        _goal_words = {"考试", "考研", "项目", "竞赛", "作业", "就业", "入门", "提升", "查漏补缺", "学懂", "掌握", "目标", "期末", "高分", "复习"}
        if any(word in text for word in _goal_words):
            segments = re.split(r"[，。,.!?！？；;]", text)
            goal_segment = ""
            for seg in segments:
                if any(word in seg for word in _goal_words):
                    goal_segment = seg.strip()
                    break
            set_fact("learning_goal", goal_segment or text)

        _cn_map = {"一": "1", "二": "2", "两": "2", "三": "3", "四": "4",
                   "五": "5", "六": "6", "七": "7", "八": "8", "九": "9"}
        time_text = re.sub(
            r"([一二两三四五六七八九])\s*个?\s*(天|周|个月|小时|分钟|星期)",
            lambda m: _cn_map[m.group(1)] + m.group(2),
            text,
        )

        daily_match = re.search(r"每天\s*(?:\d+|[一二两三四五六七八九十半]+)\s*(?:个)?小时", text)
        original_time_match = re.search(
            r"(\d+\s*个?\s*(天|日|周|星期|个月|分钟)|"
            r"[一二两三四五六七八九十半]+(?:个)?(?:天|周|星期|个月)|"
            r"一周|两周|半个月|一个月|30天|14天|两天)"
            r"(内|左右|以内|以上|完成)?",
            text,
        )
        if original_time_match:
            set_fact("time_budget", original_time_match.group(0))
        if daily_match:
            set_fact("time_budget", daily_match.group(0))
        elif not original_time_match:
            time_match = re.search(
                r"(\d+\s*个?\s*(天|日|周|星期|个月|小时|分钟)|"
                r"[一二两三四五六七八九十半]+(?:个)?(?:天|星期)|"
                r"一周|两周|半个月|一个月|半小时|一个半小时|两个小时|两小时)"
                r"(内|左右|以内|以上|完成)?",
                time_text,
            )
            if time_match:
                set_fact("time_budget", time_match.group(0))
        if "周末休息" in text:
            set_fact("time_budget", "周末休息")

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
        # Explicit facts are more precise than the broad rules above for this message.
        for key, value in extracted_profile_facts.facts.items():
            # Map daily_minutes → time_budget so PlannerAgent gets consistent data
            if key == "daily_minutes":
                state.facts["daily_minutes"] = str(value)
                existing = str(state.facts.get("time_budget", "")).strip()
                if not existing or existing in ("未提及", "待补充", "未知", "", "无"):
                    set_fact("time_budget", f"每天{int(value) // 60}小时" if int(value) >= 60 else f"每天{value}分钟")
            else:
                set_fact(key, value, force=True)
        for key, values in extracted_profile_facts.supplemental.items():
            for value in values:
                add_supplemental(key, value)

    def _set_fact(
        self,
        state: ConversationState,
        key: str,
        value: str,
        *,
        source_text: str = "",
        force: bool = False,
    ) -> None:
        if key == "target_course":
            cleaned = self._clean_course_value(value)
            if not cleaned:
                return
            old_value = state.facts.get(key, "")
            if old_value and old_value != cleaned and not force and not self._explicit_course_override(source_text):
                return
        elif key == "time_budget":
            cleaned = self._clean_time_value(value)
            if not cleaned:
                return
            old_value = state.facts.get(key, "")
            if not force:
                cleaned = self._merge_time_budget(old_value, cleaned)
        elif key == "weak_points":
            cleaned = self._clean_fact_value(value)
            if not cleaned:
                return
            old_value = state.facts.get(key, "")
            if not force:
                cleaned = self._merge_list_fact(old_value, cleaned)
        else:
            cleaned = self._clean_fact_value(value)
            if not cleaned:
                return
            old_value = state.facts.get(key, "")

        if old_value == cleaned:
            return

        conflict_reason = self._fact_conflict_reason(key, old_value, cleaned)
        if conflict_reason:
            state.last_conflicts.append({
                "key": key,
                "label": PROFILE_FIELD_DEFS.get(key, {}).get("label", key),
                "old": old_value,
                "new": cleaned,
                "reason": conflict_reason,
            })
        state.facts[key] = cleaned
        if key not in state.last_updated_fields:
            state.last_updated_fields.append(key)
        # 核心 facts 变化 → 下次需重建画像维度
        if key in _PROFILE_CORE_FIELDS:
            state.profile_dirty = True

    def _merge_time_budget(self, old_value: str, new_value: str) -> str:
        if not old_value:
            return new_value
        parts = [part.strip() for part in re.split(r"[；;]", old_value) if part.strip()]
        if any(new_value == part or new_value in part or part in new_value for part in parts):
            return old_value
        return f"{old_value}；{new_value}"

    def _merge_list_fact(self, old_value: str, new_value: str) -> str:
        if not old_value:
            return new_value
        parts = [part.strip() for part in re.split(r"[；;、,，]", old_value) if part.strip()]
        if any(new_value == part or new_value in part or part in new_value for part in parts):
            return old_value
        return f"{old_value}；{new_value}"

    def _explicit_course_override(self, text: str) -> str:
        patterns = [
            r"(?:不是学|不学|不要学)[^，。,.!?！？；;]{0,30}(?:改成|换成|改学)\s*([^，。,.!?！？；;]{2,30})",
            r"(?:现在|后面|接下来)?\s*改学\s*([^，。,.!?！？；;]{2,30})",
            r"(?:改成|换成)\s*([^，。,.!?！？；;]{2,30})",
        ]
        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                return self._clean_course_value(match.group(1))
        return ""

    def _known_course_from_text(self, text: str) -> str:
        for course in sorted(COURSE_KEYWORDS, key=len, reverse=True):
            if course in text:
                return "Python" if course.lower() == "python" else course
        return ""

    def _clean_course_value(self, value: str) -> str:
        cleaned = self._clean_fact_value(value)
        known = self._known_course_from_text(cleaned)
        if known:
            return known
        cleaned = re.sub(
            r"^(?:我(?:想|要|准备)?|想|要|准备|希望|打算|系统)?"
            r"(?:用|在)?(?:一|两|二|三|四|五|六|七|八|九|十|半|\d+)"
            r"(?:个)?(?:天|周|星期|月|个月|小时|分钟)?(?:内|左右|以内|以上)?",
            "",
            cleaned,
        ).strip()
        cleaned = re.sub(r"^(?:学|学习|复习|入门|掌握|了解|准备考|考)", "", cleaned).strip()
        cleaned = re.sub(r"^(?:从|主要是|目标|为了)", "", cleaned).strip()
        if cleaned in COURSE_STOPWORDS:
            return ""
        if any(word in cleaned for word in ["高分", "期末", "考试", "目标", "核心题型"]):
            return ""
        return cleaned

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

    def missing_fields(self, state: ConversationState, limit: int | None = None) -> list[dict[str, str]]:
        """Return fields that are either missing OR only have a shallow answer.

        Shallow fields get a follow-up probe question instead of the generic
        first-question prompt.
        """
        result: list[dict[str, str]] = []
        for key, meta in PROFILE_FIELD_DEFS.items():
            value = str(state.facts.get(key, "")).strip()
            if not value:
                result.append({
                    "key": key, "label": meta["label"], "question": meta["question"],
                })
            elif self._fact_depth(value) == "shallow":
                result.append({
                    "key": key, "label": meta["label"],
                    "question": _SHALLOW_FOLLOWUPS.get(key, f"关于{meta['label']}，能再说得具体一点吗？"),
                })
        return result if limit is None else result[:limit]

    @staticmethod
    def _fact_depth(value: str) -> str:
        """Judge whether a profile fact is shallow, moderate, or deep.

        Shallow answers like "学过一点" or "还行" don't give enough to
        personalise on.  We require concrete detail before marking a
        dimension as truly known.
        """
        text = str(value or "").strip()
        if not text:
            return "missing"
        # Very short answers are almost always shallow
        if len(text) < _SHALLOW_MIN_LENGTH:
            return "shallow"
        # Check against known shallow patterns
        for pat in _SHALLOW_PATTERNS:
            if pat in text and len(text) < len(pat) + 8:
                return "shallow"
        # Has concrete detail: specific nouns, numbers, or substantial length
        has_detail = (
            len(text) >= 20
            or bool(re.search(r"[A-Za-z+#\d]", text))  # contains English/number/symbols
            or any(word in text for word in ["专业", "工程", "计算机", "数学", "考试", "考研",
                   "期末", "项目", "每天", "小时", "周", "个月", "掌握", "熟悉", "不会", "薄弱"])
        )
        return "deep" if has_detail else "moderate"

    def readiness(self, state: ConversationState) -> dict[str, Any]:
        # Profile V2 may add normalized facts such as daily_minutes.  Readiness
        # remains a score for the legacy conversation contract only.
        filled = {
            key for key, value in state.facts.items()
            if key in PROFILE_FIELD_DEFS and value and str(value).strip()
        }
        missing_core = [key for key in CORE_FIELDS if key not in filled]

        # Depth gate: a field counts as "deep-filled" only when its value
        # is moderate or deep.  Shallow answers like "学过一点" do NOT
        # count toward readiness.
        deep_filled = {
            k for k in filled
            if self._fact_depth(state.facts.get(k, "")) in ("moderate", "deep")
        }
        shallow_fields = [
            {"key": k, "label": PROFILE_FIELD_DEFS[k]["label"], "value": state.facts[k]} if k in PROFILE_FIELD_DEFS else {"key": k, "label": k, "value": state.facts[k]}
            for k in filled if k not in deep_filled
        ]

        # True readiness: all PLAN_READY_FIELDS are deep-filled
        ready_to_plan = PLAN_READY_FIELDS.issubset(deep_filled)

        score = round(len(filled) / len(PROFILE_FIELD_DEFS), 2)
        depth_score = round(len(deep_filled) / max(1, len(PROFILE_FIELD_DEFS)), 2)

        return {
            "filledCount": len(filled),
            "deepFilledCount": len(deep_filled),
            "totalCount": len(PROFILE_FIELD_DEFS),
            "score": score,
            "depthScore": depth_score,
            "missingCore": missing_core,
            "shallowFields": shallow_fields,
            "readyToPlan": ready_to_plan,
        }

    def next_questions(self, state: ConversationState, limit: int | None = None) -> list[str]:
        """返回尚未收集的画像维度的问题列表。

        按优先级排序，limit 为 None 时返回全部缺失维度。
        调用方应自然地逐轮融入对话，而非一次性全部抛出。
        """
        missing = self.missing_fields(state)
        priority = ["background", "target_course", "knowledge_base", "weak_points", "learning_goal", "time_budget", "preference"]
        ordered = sorted(missing, key=lambda item: priority.index(item["key"]) if item["key"] in priority else 99)
        result = [item["question"] for item in ordered]
        return result if limit is None else result[:limit]

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

    def _clean_fact_value(self, value: str) -> str:
        cleaned = value.strip(" ：:，。,.!?！？；;")
        cleaned = re.sub(r"^(一下|一下子|这个|这门|这方面)", "", cleaned).strip()
        cleaned = re.sub(r"^(用|在)?(一|两|二|三|四|五|六|七|八|九|十|\d+)(天|周|个月|小时|分钟)", "", cleaned).strip()
        if cleaned in {"什么", "啥", "这个", "这些", "信息", *COURSE_STOPWORDS}:
            return ""
        return cleaned

    def _clean_time_value(self, value: str) -> str:
        return value.strip(" ：:，。,.!?！？；;")

    def _is_learning_background(self, value: str) -> bool:
        cleaned = self._clean_fact_value(value)
        if not cleaned:
            return False
        if cleaned in LOW_VALUE_BACKGROUND_WORDS:
            return False
        if len(cleaned) <= 2 and not any(hint in cleaned for hint in BACKGROUND_VALUE_HINTS):
            return False
        if not any(hint in cleaned for hint in BACKGROUND_VALUE_HINTS):
            return False
        # 额外过滤：如果值中包含明显的名字模式（如"我叫小明"），拒绝
        if self._looks_like_name_intro(cleaned):
            return False
        return True

    @staticmethod
    def _looks_like_name_intro(value: str) -> bool:
        """检测文本是否像'自我介绍名字'而非学习背景。
        例如：'我叫小明'、'叫我小王'、'名字是张三' 等。
        """
        name_intro_patterns = [
            r"我叫\S", r"叫我\S", r"名字是\S", r"称呼我?\S",
            r"我是(?:一名|一个)?(?:男生|女生|男孩子|女孩子|普通人|学生)$",
        ]
        for pat in name_intro_patterns:
            if re.search(pat, value):
                return True
        # 短文本 + 常见姓氏开头 + 无学习关键词 = 很可能是名字
        if len(value) <= 4 and not any(hint in value for hint in BACKGROUND_VALUE_HINTS):
            if value[0] in _COMMON_SURNAMES:
                return True
        return False

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
        strengths = [
            f"{re.sub(r'\s+', '', match.group(1))}：{self._level_label(match.group(0))}"
            for match in re.finditer(
                r"((?:C\s*(?:\+\+)?\s*语言|Python|Java|JavaScript)\s*基础)\s*(?:还可以|不错|较好|熟悉)",
                text,
                flags=re.IGNORECASE,
            )
        ]
        weaknesses: list[str] = []
        segments = [segment.strip() for segment in re.split(r"[，。,.!?！？；;、]", text) if segment.strip()]
        for segment in segments:
            front_missing_match = re.search(r"([A-Za-z+#一-鿿]{1,20})(?:没学过|没有学过|没学|不会|不太懂|不懂|不太会|不熟)", segment)
            if front_missing_match:
                weaknesses.append(f"{front_missing_match.group(1)}：不会/不熟")
                continue
            weak_match = re.search(r"(?:不会|不懂|没学过|没有学过|不太会|不熟)([A-Za-z+#一-鿿]{2,20})", segment)
            if weak_match:
                weaknesses.append(f"{weak_match.group(1)}：不会/不熟")
                continue
            front_weak_match = re.search(r"([A-Za-z+#一-鿿]{2,20})(?:比较|很|有点)?(?:薄弱|较弱|弱|差|一般|零基础)", segment)
            if front_weak_match:
                weaknesses.append(f"{front_weak_match.group(1)}：薄弱")
                continue
            if re.search(r"(?:C\s*(?:\+\+)?\s*语言|Python|Java|JavaScript)\s*基础\s*(?:还可以|不错|较好|熟悉)", segment, flags=re.IGNORECASE):
                continue
            strength_match = re.search(r"([A-Za-z+#一-鿿]{2,20}?)(?:还可以|可以|较好|不错|熟悉|会)", segment)
            if strength_match:
                topic = strength_match.group(1).rstrip("还也都很较比较")
                strengths.append(f"{topic}：{self._level_label(segment)}")
        return list(dict.fromkeys(strengths)), list(dict.fromkeys(weaknesses))

    def _level_label(self, segment: str) -> str:
        if any(word in segment for word in ["较好", "不错", "熟悉"]):
            return "较好"
        if "还可以" in segment or "可以" in segment:
            return "还可以"
        return "会"


conversation_store = ConversationStore()
