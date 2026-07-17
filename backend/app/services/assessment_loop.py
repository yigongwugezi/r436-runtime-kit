"""
Closed-loop learning assessment scheduler.

Bridges the gap between discrete agent capabilities and a continuous
assess → adjust → notify cycle:

1. **Event-driven triggers** — fired after quiz submission / resource completion.
2. **Periodic re-assessment** — background task checks for stale diagnoses.
3. **Mastery-change detection** — compares new vs. old mastery to decide
   whether plan adjustment is warranted.
4. **Notification store** — lightweight in-memory queue the frontend polls.

All heavy work (LLM calls) is delegated to existing agents/services;
this module only orchestrates *when* to call them.
"""

from __future__ import annotations

import asyncio
import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Any

from app.db.engine import SessionLocal

logger = logging.getLogger(__name__)

# ── Thresholds ───────────────────────────────────────────────────────────

REASSESS_INTERVAL_SECONDS = 24 * 3600       # re-assess every 1 day
MIN_EVENTS_FOR_REASSESS = 3                  # need at least N new events to re-assess
RESOURCE_COMPLETE_BATCH = 3                  # auto-diagnose after every N resource completions


def _dynamic_threshold(score: float) -> int:
    """根据当前分数和配置返回动态阈值。分数越低阈值越小，越容易触发调整。

    阈值通过 settings.mastery_threshold_* 配置，可在 .env 或运行时调整。
    """
    from app.config import settings
    if score < 30:
        return settings.mastery_threshold_low
    elif score < 60:
        return settings.mastery_threshold_mid
    elif score < 80:
        return settings.mastery_threshold_high
    return settings.mastery_threshold_top


# ── Notification store ───────────────────────────────────────────────────


@dataclass
class AssessmentNotification:
    type: str  # "diagnosis_updated" | "plan_adjusted" | "recommendations_ready" | "review_needed"
    title: str
    message: str
    session_id: str
    created_at: float = field(default_factory=time.time)


class NotificationStore:
    """Thread-safe in-memory notification queue with SSE subscriber support."""

    def __init__(self) -> None:
        self._notifications: dict[str, list[AssessmentNotification]] = {}
        self._subscribers: dict[str, list[asyncio.Queue]] = {}
        self._lock = threading.Lock()

    def subscribe(self, session_id: str) -> asyncio.Queue:
        """Register an async subscriber for real-time SSE push."""
        q: asyncio.Queue = asyncio.Queue(maxsize=100)
        with self._lock:
            self._subscribers.setdefault(session_id, []).append(q)
        return q

    def unsubscribe(self, session_id: str, queue: asyncio.Queue) -> None:
        """Remove an async subscriber."""
        with self._lock:
            subs = self._subscribers.get(session_id, [])
            if queue in subs:
                subs.remove(queue)

    def push(self, session_id: str, notification: AssessmentNotification) -> None:
        with self._lock:
            self._notifications.setdefault(session_id, []).append(notification)
            if len(self._notifications[session_id]) > 20:
                self._notifications[session_id] = self._notifications[session_id][-20:]
            subs = list(self._subscribers.get(session_id, []))
        for q in subs:
            try:
                q.put_nowait({
                    "type": notification.type,
                    "title": notification.title,
                    "message": notification.message,
                    "sessionId": notification.session_id,
                    "createdAt": notification.created_at,
                })
            except asyncio.QueueFull:
                pass

    def pop_all(self, session_id: str) -> list[dict[str, Any]]:
        with self._lock:
            items = self._notifications.pop(session_id, [])
            return [
                {
                    "type": n.type,
                    "title": n.title,
                    "message": n.message,
                    "sessionId": n.session_id,
                    "createdAt": n.created_at,
                }
                for n in items
            ]

    def has_pending(self, session_id: str) -> bool:
        with self._lock:
            return bool(self._notifications.get(session_id))


notification_store = NotificationStore()


# ── State tracking (in-memory; survives within a single process lifetime) ──


@dataclass
class SessionAssessmentState:
    session_id: str
    last_diagnosis_at: float = 0.0
    last_mastery_snapshot: dict[str, float] = field(default_factory=dict)  # kp_name → score
    events_since_last_diagnosis: int = 0
    resource_completions_since_diagnosis: int = 0


class AssessmentStateTracker:
    """Tracks per-session assessment metadata to decide when to trigger.

    State is persisted to DB via ``AssessmentStateModel`` so that event
    counters, mastery snapshots, and diagnosis timestamps survive server
    restarts.  An in-memory cache avoids repeated DB reads within the same
    process lifetime.
    """

    def __init__(self) -> None:
        self._cache: dict[str, SessionAssessmentState] = {}
        self._lock = threading.Lock()

    # ── DB helpers ──────────────────────────────────────────────────

    @staticmethod
    def _db_session():
        from app.db.engine import SessionLocal
        return SessionLocal()

    def _load_from_db(self, session_id: str) -> SessionAssessmentState | None:
        try:
            db = self._db_session()
            from app.db.repository import get_assessment_state
            row = get_assessment_state(db, session_id)
            if row is None:
                return None
            return SessionAssessmentState(
                session_id=row.session_id,
                last_diagnosis_at=row.last_diagnosis_at,
                last_mastery_snapshot=dict(row.last_mastery_snapshot or {}),
                events_since_last_diagnosis=row.events_since_last_diagnosis,
                resource_completions_since_diagnosis=row.resource_completions_since_diagnosis,
            )
        except Exception:
            return None
        finally:
            if db:
                db.close()

    def _persist(self, state: SessionAssessmentState) -> None:
        try:
            db = self._db_session()
            from app.db.repository import upsert_assessment_state
            upsert_assessment_state(
                db, state.session_id,
                last_diagnosis_at=state.last_diagnosis_at,
                last_mastery_snapshot=state.last_mastery_snapshot,
                events_since_last_diagnosis=state.events_since_last_diagnosis,
                resource_completions_since_diagnosis=state.resource_completions_since_diagnosis,
            )
        except Exception:
            logger.exception("Failed to persist assessment state for %s", state.session_id)
        finally:
            if db:
                db.close()

    # ── Public API ──────────────────────────────────────────────────

    def get(self, session_id: str) -> SessionAssessmentState:
        with self._lock:
            if session_id in self._cache:
                return self._cache[session_id]
        # Try DB, fall back to fresh in-memory
        db_state = self._load_from_db(session_id)
        state = db_state if db_state is not None else SessionAssessmentState(session_id=session_id)
        with self._lock:
            self._cache[session_id] = state
        return state

    def record_diagnosis(self, session_id: str, mastery: dict[str, float]) -> None:
        with self._lock:
            state = self._cache.get(session_id) or SessionAssessmentState(session_id=session_id)
            state.last_diagnosis_at = time.time()
            state.last_mastery_snapshot = dict(mastery)
            state.events_since_last_diagnosis = 0
            state.resource_completions_since_diagnosis = 0
            self._cache[session_id] = state
        self._persist(state)

    def record_event(self, session_id: str, event_type: str) -> None:
        with self._lock:
            state = self._cache.get(session_id)
            if state is None:
                db_state = self._load_from_db(session_id)
                state = db_state if db_state is not None else SessionAssessmentState(session_id=session_id)
            state.events_since_last_diagnosis += 1
            if event_type == "resource_complete":
                state.resource_completions_since_diagnosis += 1
            self._cache[session_id] = state
        self._persist(state)

    def needs_reassessment(self, session_id: str) -> bool:
        state = self.get(session_id)
        if state.last_diagnosis_at == 0:
            return state.events_since_last_diagnosis >= MIN_EVENTS_FOR_REASSESS
        time_since = time.time() - state.last_diagnosis_at
        has_enough_events = state.events_since_last_diagnosis >= MIN_EVENTS_FOR_REASSESS
        return time_since >= REASSESS_INTERVAL_SECONDS and has_enough_events

    def needs_post_quiz_diagnosis(self, session_id: str) -> bool:
        """Should we auto-diagnose after a quiz submission?  Always true after a quiz."""
        return True

    def needs_post_resource_diagnosis(self, session_id: str) -> bool:
        """Should we auto-diagnose after resource completions?"""
        state = self.get(session_id)
        return state.resource_completions_since_diagnosis >= RESOURCE_COMPLETE_BATCH

    def get_stale_sessions(self) -> list[str]:
        """Return sessions that are due for periodic re-assessment (DB-backed)."""
        try:
            db = self._db_session()
            from app.db.repository import get_stale_assessment_sessions
            return get_stale_assessment_sessions(db, REASSESS_INTERVAL_SECONDS)
        except Exception:
            logger.exception("Failed to query stale assessment sessions")
            return []
        finally:
            if db:
                db.close()


assessment_tracker = AssessmentStateTracker()


# ── Core closed-loop functions ───────────────────────────────────────────


def _get_or_create_factory():
    """Get or create a shared AgentFactory with LLM client for this process."""
    from app.services.agent_factory import AgentFactory
    from app.services.llm_client import get_llm_client
    return AgentFactory(llm_client=get_llm_client())


def _trigger_assessment_recommendations(
    session_id: str, diagnosis: dict | None, assessment: dict
) -> None:
    """根据评估结果重新生成推荐。"""
    try:
        from app.services.assessment_loop import _generate_recommendations
        _generate_recommendations(session_id, diagnosis, assessment=assessment)
    except Exception:
        pass


def _trigger_assessment_path_adjustment(
    session_id: str, scores: dict, profile: dict | None
) -> None:
    """根据评估结果和阈值决定是否调路径。"""
    try:
        from app.db.engine import SessionLocal
        from app.db.repository import get_latest_learning_path
        from app.agents.planner_agent import PlannerAgent
        from app.services.agent_factory import AgentFactory
        db2 = SessionLocal()
        try:
            path_model = get_latest_learning_path(db2, session_id)
            existing = path_model.stages if path_model else []
        finally:
            db2.close()
        if not existing:
            return
        old_mastery = assessment_tracker.get(session_id).last_mastery_snapshot
        needs_adjust = True
        if old_mastery:
            significant = 0
            for k, v in scores.items():
                if v is None:
                    continue
                old = old_mastery.get(k, 50)
                if abs(v - old) >= _dynamic_threshold(old):
                    significant += 1
            needs_adjust = significant >= 1
        if needs_adjust:
            assessment_diagnosis = {
                "mastery_levels": [
                    {"name": k, "score": v}
                    for k, v in scores.items() if v is not None
                ],
                "diagnosis_summary": "LLM评估驱动调整",
            }
            factory = AgentFactory()
            planner = factory.get("planner_agent")
            if planner and existing:
                pr = planner.run({
                    "mode": "adjust",
                    "session_id": session_id,
                    "diagnosis": assessment_diagnosis,
                    "profile": profile or {},
                    "existing_path": existing,
                })
                if pr.get("learning_path"):
                    from app.services.conversation_state import conversation_store
                    cs = conversation_store.get_state_or_none(session_id)
                    if cs:
                        cs.last_result = dict(cs.last_result or {})
                        cs.last_result["learning_path"] = pr["learning_path"]
                        # Persist to DB so path page reflects adjustment
                        conversation_store.set_result(session_id, cs.last_result)
                        # 加速再评估
                        import time as _t
                        state = assessment_tracker.get(session_id)
                        state.last_diagnosis_at = _t.time() - 2 * 24 * 3600
                        assessment_tracker._persist(state)
        # 无条件保存评估分数
        state = assessment_tracker.get(session_id)
        state.last_mastery_snapshot = {k: v for k, v in scores.items() if v is not None}
        assessment_tracker._persist(state)
    except Exception:
        pass



def _trigger_llm_assessment(session_id: str) -> None:
    """异步触发 LLM 多维度评估并推送通知。"""
    try:
        from app.services.llm_assessment import run_llm_assessment
        from app.db.engine import SessionLocal
        from app.db.repository import get_event_analytics, get_latest_profile
        from app.services.conversation_state import conversation_store
        db = SessionLocal()
        try:
            analytics = get_event_analytics(db, session_id)
            profile_snapshot = get_latest_profile(db, session_id)
            profile = {"dimensions": profile_snapshot.dimensions} if profile_snapshot else None
        finally:
            db.close()
        cs = conversation_store.get_state_or_none(session_id)
        diagnosis = None
        if cs and cs.last_result:
            diagnosis = cs.last_result.get("diagnosis")
        result = run_llm_assessment(
            session_id=session_id, profile=profile, analytics=analytics, diagnosis=diagnosis
        )
        if result.get("status") != "completed" or not result.get("scores"):
            return
        # 推通知
        from app.services.assessment_loop import notification_store, AssessmentNotification
        scores = result["scores"]
        avg_score = sum(scores.values()) / len(scores) if scores else 0
        notification_store.push(
            session_id,
            AssessmentNotification(
                type="diagnosis_updated",
                title="AI 学习评估完成",
                message=f"综合评分 {avg_score:.0f}/100。{result['summary'][:80]}",
                session_id=session_id,
            ),
        )
        # 重新生成推荐
        _trigger_assessment_recommendations(session_id, diagnosis, result)
        # 路径调整
        _trigger_assessment_path_adjustment(session_id, scores, profile)
    except Exception as exc:
        logger.debug("LLM assessment trigger skipped: %s", exc)


def run_post_quiz_assessment(
    session_id: str,
    quiz_title: str = "",
    quiz_score: int | None = None,
    weak_points: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Run the FULL closed-loop assessment after a quiz is submitted.

    Closed-loop sequence:
      诊断(DiagnosisAgent) → 画像更新(ProfileAgent) → 路径调整(PlannerAgent)
      → 资源生成(ResourceAgent) → 推荐(RecommendationEngine)

    Called synchronously from the assessment router (fire-and-forget pattern
    recommended so HTTP response is not delayed).

    Returns a summary dict for logging / notification purposes.
    """
    logger.info(
        "Post-quiz assessment triggered for session=%s, quiz=%s, score=%s",
        session_id, quiz_title, quiz_score,
    )

    profile_updated = False
    path_adjusted = False
    resources_generated = 0

    try:
        # ═══════════════════════════════════════════════════════════
        # Step 1: Gather context
        # ═══════════════════════════════════════════════════════════
        diagnosis_context = _build_diagnosis_context(session_id)

        # ═══════════════════════════════════════════════════════════
        # Step 2: Run DiagnosisAgent (with LLM)
        # ═══════════════════════════════════════════════════════════
        factory = _get_or_create_factory()
        diagnosis_agent = factory.get("diagnosis_agent")
        if diagnosis_agent is None:
            from app.agents.diagnosis_agent import DiagnosisAgent
            diagnosis_agent = DiagnosisAgent(mock_data={})
        result = diagnosis_agent.run(diagnosis_context)
        new_diagnosis = result.get("diagnosis", {})

        # Extract mastery levels for change detection
        mastery_levels = new_diagnosis.get("mastery_levels", [])
        new_mastery: dict[str, float] = {
            m.get("name", ""): float(m.get("score", 50))
            for m in mastery_levels
        }

        # Persist diagnosis to conversation state
        from app.services.conversation_state import conversation_store
        conversation_store.set_diagnosis(session_id, new_diagnosis)

        # ═══════════════════════════════════════════════════════════
        # Step 3: Update ProfileAgent — 画像随学随新
        # ═══════════════════════════════════════════════════════════
        try:
            profile_agent = factory.get("profile_agent")
            if profile_agent is not None:
                profile_context = {
                    "session_id": session_id,
                    "user_message": f"小测「{quiz_title}」完成，得分{quiz_score or 'N/A'}",
                    "profile_facts": diagnosis_context.get("profile_facts", {}),
                    "diagnosis": new_diagnosis,
                    "course": diagnosis_context.get("course"),
                    "weak_points": weak_points or [],
                }
                profile_result = profile_agent.run(profile_context)
                updated_profile = profile_result.get("profile", {})
                if updated_profile:
                    conversation_store.set_result(session_id, {
                        "profile": updated_profile,
                        "diagnosis": new_diagnosis,
                    })
                    profile_updated = True
                    logger.info(
                        "ProfileAgent updated for session=%s, dimensions=%d",
                        session_id, len(updated_profile),
                    )
        except Exception:
            logger.exception("ProfileAgent update failed for session=%s", session_id)

        # ═══════════════════════════════════════════════════════════
        # Step 4: Check if plan adjustment is needed → PlannerAgent
        #
        # Trigger adjustment when:
        #   a) mastery scores changed significantly (≥1 topic, ≥10 pts), OR
        #   b) the diagnosis revealed actionable weak points that the
        #      current path may not cover
        # ═══════════════════════════════════════════════════════════
        mastery_changed = _detect_mastery_change(session_id, new_mastery)
        new_weak_points = new_diagnosis.get("weak_knowledge_points", [])
        has_actionable_weakness = bool(new_weak_points or weak_points)
        should_adjust = mastery_changed or has_actionable_weakness
        if should_adjust:
            try:
                planner_agent = factory.get("planner_agent")
                if planner_agent is not None:
                    planner_context = {
                        "session_id": session_id,
                        "mode": "adjust",
                        "user_message": f"基于小测「{quiz_title}」结果调整学习路径",
                        "diagnosis": new_diagnosis,
                        "profile": diagnosis_context.get("profile", {}),
                        "profile_facts": diagnosis_context.get("profile_facts", {}),
                        "existing_path": diagnosis_context.get("learning_path", []),
                    }
                    planner_result = planner_agent.run(planner_context)
                    adjusted_path = planner_result.get("learning_path", [])
                    if adjusted_path:
                        # ── 不直接覆盖，创建 pending_revision ──
                        from app.services.day_planner import compute_diff
                        existing_path = diagnosis_context.get("learning_path", [])
                        diff = compute_diff(existing_path, adjusted_path)
                        conversation_store.set_pending_revision(
                            session_id,
                            proposed_stages=adjusted_path,
                            diff=diff,
                            reason=f"基于小测「{quiz_title}」结果调整学习路径",
                        )
                        path_adjusted = True
                        logger.info(
                            "PlannerAgent created pending revision for session=%s, diff=%s",
                            session_id, diff.get("summary", ""),
                        )
            except Exception:
                logger.exception("PlannerAgent adjustment failed for session=%s", session_id)

        # ═══════════════════════════════════════════════════════════
        # Step 5: ResourceAgent — 为薄弱点生成针对性资源
        # ═══════════════════════════════════════════════════════════
        weak_kps = new_diagnosis.get("weak_knowledge_points", [])
        if weak_kps:
            try:
                resource_agent = factory.get("resource_agent")
                if resource_agent is not None:
                    resource_context = {
                        "session_id": session_id,
                        "user_message": f"为以下薄弱知识点生成针对性学习资源：{', '.join(w.get('name', '') for w in weak_kps[:5] if w.get('name'))}",
                        "diagnosis": new_diagnosis,
                        "profile": diagnosis_context.get("profile", {}),
                        "profile_facts": diagnosis_context.get("profile_facts", {}),
                        "knowledge_points": [w.get("name", "") for w in weak_kps[:5] if w.get("name")],
                        "resources": diagnosis_context.get("resources", []),
                    }
                    resource_result = resource_agent.run(resource_context)
                    new_resources = resource_result.get("resources", [])
                    if new_resources:
                        # Persist generated resources into conversation state
                        existing_result = dict(conversation_store.get(session_id).last_result or {})
                        existing_resources = list(existing_result.get("resources", []))
                        existing_resources.extend(new_resources)
                        existing_result["resources"] = existing_resources
                        conversation_store.set_result(session_id, existing_result)
                        resources_generated = len(new_resources)
                        logger.info(
                            "ResourceAgent generated %d resources for session=%s",
                            resources_generated, session_id,
                        )
            except Exception:
                logger.exception("ResourceAgent generation failed for session=%s", session_id)

        # ═══════════════════════════════════════════════════════════
        # Step 6: Generate recommendations
        # ═══════════════════════════════════════════════════════════
        recommendations = _generate_recommendations(session_id, new_diagnosis)

        # ═══════════════════════════════════════════════════════════
        # Step 7: Notify frontend
        # ═══════════════════════════════════════════════════════════
        weak_topic_names = [
            w.get("name", w.get("topic", ""))
            for w in (new_diagnosis.get("weak_knowledge_points") or [])[:3]
        ]

        notification_store.push(session_id, AssessmentNotification(
            type="diagnosis_updated",
            title="学习诊断已更新",
            message=(
                f"「{quiz_title}」已完成（得分 {quiz_score or 'N/A'}）。"
                f"诊断发现 {len(new_diagnosis.get('weak_knowledge_points', []))} 个需要关注的知识点"
                f"{'：' + '、'.join(weak_topic_names) if weak_topic_names else ''}。"
            ),
            session_id=session_id,
        ))

        if should_adjust:
            notification_store.push(session_id, AssessmentNotification(
                type="plan_adjusted",
                title="学习路径已自动调整",
                message=(
                    "你的知识掌握情况发生了显著变化，"
                    "学习路径已自动调整以匹配当前水平。"
                ),
                session_id=session_id,
            ))

        if resources_generated > 0:
            notification_store.push(session_id, AssessmentNotification(
                type="recommendations_ready",
                title="针对性学习资源已生成",
                message=f"基于诊断结果，为你生成了 {resources_generated} 个针对性学习资源。",
                session_id=session_id,
            ))

        if recommendations:
            notification_store.push(session_id, AssessmentNotification(
                type="recommendations_ready",
                title="新的学习推荐已生成",
                message=f"基于最新诊断，为你推荐 {len(recommendations)} 个学习行动。",
                session_id=session_id,
            ))

        # ═══════════════════════════════════════════════════════════
        # Step 8: Update tracking state
        # ═══════════════════════════════════════════════════════════
        assessment_tracker.record_diagnosis(session_id, new_mastery)

        # ── Step 9: LLM 多维度学习评估（异步触发，不阻塞主流程）──
        _th = threading.Thread(
            target=_trigger_llm_assessment,
            args=(session_id,),
            daemon=True,
        )
        _th.start()

        return {
            "diagnosis_ran": True,
            "mastery_levels_count": len(mastery_levels),
            "weak_points_count": len(new_diagnosis.get("weak_knowledge_points", [])),
            "recommendations_count": len(recommendations),
            "plan_adjustment_needed": should_adjust,
            "profile_updated": profile_updated,
            "path_adjusted": path_adjusted,
            "resources_generated": resources_generated,
        }

    except Exception:
        logger.exception("Post-quiz assessment failed for session=%s", session_id)
        return {"diagnosis_ran": False, "error": "Assessment loop failed"}


def run_periodic_reassessment(session_id: str) -> dict[str, Any]:
    """Run a scheduled re-assessment for a session — full closed loop.

    Called by the background scheduler.  Checks whether knowledge has decayed,
    updates profile, adjusts path, generates resources, and pushes notifications.
    """
    logger.info("Periodic re-assessment triggered for session=%s", session_id)

    profile_updated = False
    path_adjusted = False

    try:
        # 1. Build context and run diagnosis (with LLM)
        diagnosis_context = _build_diagnosis_context(session_id)
        factory = _get_or_create_factory()
        diagnosis_agent = factory.get("diagnosis_agent")
        if diagnosis_agent is None:
            from app.agents.diagnosis_agent import DiagnosisAgent
            diagnosis_agent = DiagnosisAgent(mock_data={})
        result = diagnosis_agent.run(diagnosis_context)
        new_diagnosis = result.get("diagnosis", {})

        # 2. Extract mastery
        mastery_levels = new_diagnosis.get("mastery_levels", [])
        new_mastery: dict[str, float] = {
            m.get("name", ""): float(m.get("score", 50))
            for m in mastery_levels
        }

        # 3. Persist
        from app.services.conversation_state import conversation_store
        conversation_store.set_diagnosis(session_id, new_diagnosis)

        # 4. Update ProfileAgent — 画像随学随新
        try:
            profile_agent = factory.get("profile_agent")
            if profile_agent is not None:
                profile_result = profile_agent.run({
                    "session_id": session_id,
                    "user_message": "定期学习诊断更新",
                    "profile_facts": diagnosis_context.get("profile_facts", {}),
                    "diagnosis": new_diagnosis,
                })
                updated_profile = profile_result.get("profile", {})
                if updated_profile:
                    conversation_store.set_result(session_id, {
                        "profile": updated_profile,
                        "diagnosis": new_diagnosis,
                    })
                    profile_updated = True
        except Exception:
            logger.exception("ProfileAgent update failed in periodic reassessment")

        # 5. Detect decay (knowledge forgotten over time)
        old_mastery = assessment_tracker.get(session_id).last_mastery_snapshot
        decayed_topics = _detect_decay(old_mastery, new_mastery)

        # 6. Generate recommendations
        recommendations = _generate_recommendations(session_id, new_diagnosis)

        # 7. Check plan adjustment → PlannerAgent
        should_adjust = _detect_mastery_change(session_id, new_mastery)
        if should_adjust:
            try:
                planner_agent = factory.get("planner_agent")
                if planner_agent is not None:
                    planner_result = planner_agent.run({
                        "session_id": session_id,
                        "mode": "adjust",
                        "user_message": "定期诊断发现掌握度变化，调整学习路径",
                        "diagnosis": new_diagnosis,
                        "profile": diagnosis_context.get("profile", {}),
                        "profile_facts": diagnosis_context.get("profile_facts", {}),
                        "existing_path": diagnosis_context.get("learning_path", []),
                    })
                    adjusted_path = planner_result.get("learning_path", [])
                    if adjusted_path:
                        from app.services.day_planner import compute_diff
                        existing_path = diagnosis_context.get("learning_path", [])
                        diff = compute_diff(existing_path, adjusted_path)
                        conversation_store.set_pending_revision(
                            session_id,
                            proposed_stages=adjusted_path,
                            diff=diff,
                            reason="定期诊断发现掌握度变化",
                        )
                        path_adjusted = True
            except Exception:
                logger.exception("PlannerAgent failed in periodic reassessment")

        # 8. Notify
        if decayed_topics:
            topic_names = "、".join(decayed_topics[:3])
            notification_store.push(session_id, AssessmentNotification(
                type="review_needed",
                title="检测到知识遗忘",
                message=f"以下知识点掌握度下降：{topic_names}。已自动调整复习计划。",
                session_id=session_id,
            ))

        notification_store.push(session_id, AssessmentNotification(
            type="diagnosis_updated",
            title="定期诊断已更新",
            message=f"完成定期学习诊断。当前掌握 {len([m for m in mastery_levels if m.get('level') in ('精通', '熟练')])} 个知识点。",
            session_id=session_id,
        ))

        if should_adjust and not decayed_topics:
            notification_store.push(session_id, AssessmentNotification(
                type="plan_revision_ready",
                title="路径调整建议待确认",
                message="定期检查发现你的学习进度已发生变化，学习路径已自动更新。",
                session_id=session_id,
            ))

        assessment_tracker.record_diagnosis(session_id, new_mastery)

        return {
            "diagnosis_ran": True,
            "decayed_topics": decayed_topics,
            "plan_adjustment_needed": should_adjust,
            "profile_updated": profile_updated,
            "path_adjusted": path_adjusted,
            "recommendations_count": len(recommendations),
        }

    except Exception:
        logger.exception("Periodic re-assessment failed for session=%s", session_id)
        return {"diagnosis_ran": False, "error": "Re-assessment failed"}


def run_resource_completion_check(session_id: str, resource_id: str = "") -> dict[str, Any]:
    """Check if enough resources have been completed to warrant re-diagnosis.

    Called from learning_tracker.log() when event_type == 'resource_complete'.
    """
    assessment_tracker.record_event(session_id, "resource_complete")
    _increment_event_counter(session_id)

    if assessment_tracker.needs_post_resource_diagnosis(session_id):
        logger.info(
            "Resource completion threshold reached for session=%s (resource=%s)",
            session_id, resource_id,
        )
        return run_post_quiz_assessment(
            session_id,
            quiz_title=f"完成资源 {resource_id}" if resource_id else "资源学习",
        )
    return {"diagnosis_ran": False, "reason": "threshold not reached"}


def record_learning_event(session_id: str, event_type: str) -> None:
    """Record any learning event for the assessment tracker.

    Call this from learning_tracker.log() for all event types.
    """
    assessment_tracker.record_event(session_id, event_type)


# ── Internal helpers ─────────────────────────────────────────────────────


def _build_diagnosis_context(session_id: str) -> dict[str, Any]:
    """Build the diagnostic context dict expected by DiagnosisAgent.run()."""
    from app.services.conversation_state import conversation_store
    from app.services.agent_service import (
        get_analytics,
        get_learning_path,
        get_profile,
        get_resources,
    )

    state = conversation_store.get(session_id)
    cached = state.last_result or {}

    try:
        analytics = get_analytics(session_id)
    except Exception:
        analytics = {}

    try:
        stored_path = get_learning_path(session_id)
    except Exception:
        stored_path = None

    try:
        stored_resources = get_resources(session_id)
    except Exception:
        stored_resources = []

    profile = cached.get("profile") or (
        (get_profile(session_id) or {}).get("dimensions", [])
    )

    return {
        "session_id": session_id,
        "user_message": "自动诊断触发（测验/资源完成后）",
        "profile": profile,
        "profile_facts": dict(state.facts),
        "learning_path": (stored_path or {}).get("stages", []) if stored_path else [],
        "resources": stored_resources or cached.get("resources", []),
        "knowledge_context": cached.get("knowledge_context") or {},
        "analytics": analytics,
    }


def _generate_recommendations(
    session_id: str,
    diagnosis: dict[str, Any],
    assessment: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Generate structured recommendations based on the latest diagnosis."""
    try:
        from app.services.agent_service import get_resources, get_learning_path
        from app.services.recommendation_engine import generate_recommendations
        from app.db.engine import SessionLocal
        from app.db.models import ResourceModel, LearningPathModel

        db = SessionLocal()
        try:
            resources = db.query(ResourceModel).filter(
                ResourceModel.session_id == session_id
            ).all()

            path = db.query(LearningPathModel).filter(
                LearningPathModel.session_id == session_id
            ).order_by(LearningPathModel.created_at.desc()).first()

            weak_topics = diagnosis.get("weak_knowledge_points", [])
            if not weak_topics:
                weak_topics = diagnosis.get("weak_topics", [])

            # Convert weak_knowledge_points to weak_topics format
            normalized_weak_topics = []
            for w in weak_topics:
                normalized_weak_topics.append({
                    "topic": w.get("name", w.get("topic", "")),
                    "wrongCount": w.get("error_count", w.get("wrongCount", 1)),
                    "totalCount": w.get("total_attempts", w.get("totalCount", 2)),
                    "risk": w.get("error_rate", w.get("risk", 0.5)),
                })

            return generate_recommendations(
                session_id=session_id,
                weak_topics=normalized_weak_topics,
                resources=resources,
                learning_path=path,
                assessment=assessment,
                db=db,
            )
        finally:
            db.close()
    except Exception:
        logger.exception("Failed to generate recommendations for session=%s", session_id)
        return []


def _detect_mastery_change(
    session_id: str,
    new_mastery: dict[str, float],
) -> bool:
    """Detect if mastery has changed enough to warrant plan adjustment."""
    old_mastery = assessment_tracker.get(session_id).last_mastery_snapshot
    if not old_mastery:
        return False  # No baseline yet

    # Check significant changes
    significant_changes = 0
    for kp_name, new_score in new_mastery.items():
        old_score = old_mastery.get(kp_name, 50)  # default to neutral
        if abs(new_score - old_score) >= _dynamic_threshold(old_score):
            significant_changes += 1

    # Trigger if 1+ topics changed significantly (was 3 — too conservative)
    return significant_changes >= 1


def _detect_decay(
    old_mastery: dict[str, float],
    new_mastery: dict[str, float],
) -> list[str]:
    """Detect knowledge points where mastery has declined significantly."""
    decayed = []
    for kp_name, old_score in old_mastery.items():
        new_score = new_mastery.get(kp_name, old_score)
        if old_score - new_score >= _dynamic_threshold(old_score):
            decayed.append(kp_name)
    return sorted(decayed, key=lambda n: old_mastery.get(n, 0) - new_mastery.get(n, 0), reverse=True)


# ── Background scheduler ─────────────────────────────────────────────────

_scheduler_task: Any = None
_scheduler_stop: threading.Event | None = None


def _increment_event_counter(session_id: str) -> None:
    """Increment the event counter without the full resource_complete logic."""
    assessment_tracker.record_event(session_id, "generic")


async def _periodic_reassessment_loop(stop_event: threading.Event, interval: int = 600) -> None:
    """Background loop that periodically checks for stale sessions.

    Runs every `interval` seconds (default 10 min).  For each stale session,
    runs a lightweight re-assessment.
    """
    logger.info("Background re-assessment scheduler started (interval=%ss)", interval)
    while not stop_event.is_set():
        try:
            stale_sessions = assessment_tracker.get_stale_sessions()
            if stale_sessions:
                logger.info("Found %d stale session(s) for re-assessment", len(stale_sessions))
                for sid in stale_sessions[:5]:  # Limit per cycle to avoid overload
                    try:
                        run_periodic_reassessment(sid)
                    except Exception:
                        logger.exception("Re-assessment failed for session=%s", sid)
        except Exception:
            logger.exception("Error in periodic re-assessment loop")

        # Sleep in small chunks so we can stop promptly
        for _ in range(interval):
            if stop_event.is_set():
                break
            await _sleep_async(1)


async def _sleep_async(seconds: float) -> None:
    """Async sleep helper."""
    import asyncio
    await asyncio.sleep(seconds)


def start_background_scheduler() -> None:
    """Start the periodic re-assessment background task.

    Called from main.py lifespan startup.  Safe to call multiple times.
    """
    global _scheduler_task, _scheduler_stop
    import asyncio

    if _scheduler_task is not None:
        return

    _scheduler_stop = threading.Event()
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            _scheduler_task = asyncio.ensure_future(
                _periodic_reassessment_loop(_scheduler_stop)
            )
        else:
            _scheduler_task = asyncio.run_coroutine_threadsafe(
                _periodic_reassessment_loop(_scheduler_stop), loop
            )
        logger.info("Background scheduler started")
    except RuntimeError:
        # No event loop yet — will be started on first request
        logger.info("Background scheduler deferred (no event loop)")


def stop_background_scheduler() -> None:
    """Stop the periodic re-assessment background task."""
    global _scheduler_task, _scheduler_stop
    if _scheduler_stop is not None:
        _scheduler_stop.set()
    if _scheduler_task is not None and not _scheduler_task.done():
        try:
            _scheduler_task.cancel()
        except Exception:
            pass
    _scheduler_task = None
    _scheduler_stop = None
    logger.info("Background scheduler stopped")


def ensure_scheduler_running() -> None:
    """Idempotent start — call from lifespan or first request."""
    global _scheduler_task
    if _scheduler_task is None or _scheduler_task.done():
        start_background_scheduler()
