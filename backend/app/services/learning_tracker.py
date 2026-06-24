"""Learning event tracker with DB persistence.

Wraps the same public API as the original in-memory tracker but delegates
storage and analytics queries to the database when ``enable_db()`` has been
called.
"""

import logging
import time
from typing import Any

from sqlalchemy.orm import Session

from app.db.engine import SessionLocal
from app.db.repository import get_event_analytics, get_events, log_event, delete_session
from app.utils.errors import MissingSessionIdError

logger = logging.getLogger(__name__)


class LearningTracker:
    """Tracks learning events with optional DB persistence.

    Call ``enable_db()`` once at application startup to persist events
    across restarts.  Without it the tracker falls back to in-memory
    operation (useful for tests).
    """

    def __init__(self) -> None:
        self._events: list[dict[str, Any]] = []
        self._db_enabled: bool = False

    def enable_db(self) -> None:
        self._db_enabled = True

    def _db_session(self) -> Session:
        return SessionLocal()

    # ── Public API ────────────────────────────────────────────────────

    def log(self, event: dict[str, Any], session_id: str | None = None) -> dict[str, Any]:
        sid = session_id or event.get("sessionId") or ""
        if not sid or not sid.strip():
            raise MissingSessionIdError()
        normalized = {
            **event,
            "sessionId": sid.strip(),
            "timestamp": event.get("timestamp") or time.time(),
        }

        if self._db_enabled:
            try:
                db = self._db_session()
                log_event(
                    db,
                    session_id=normalized["sessionId"],
                    event_type=str(event.get("event", "generic")),
                    resource_id=event.get("resourceId"),
                    metadata=event.get("metadata", event),
                )
            finally:
                db.close()

        # Always keep in-memory cache for backward compat
        self._events.append(normalized)
        return normalized

    def recent(self, session_id: str | None = None, limit: int = 10) -> list[dict[str, Any]]:
        if self._db_enabled:
            try:
                db = self._db_session()
                events = get_events(db, session_id, limit=limit)
                return [
                    {
                        "event": evt.event_type,
                        "resourceId": evt.resource_id,
                        "metadata": evt.metadata_ or {},
                        "sessionId": evt.session_id,
                        "timestamp": evt.created_at.timestamp() if evt.created_at else time.time(),
                    }
                    for evt in events
                ]
            finally:
                db.close()

        filtered = self._filter(session_id)
        return filtered[-limit:]

    def summary(self, session_id: str | None = None) -> dict[str, Any]:
        if not session_id or not session_id.strip():
            return {}
        if self._db_enabled:
            try:
                db = self._db_session()
                return get_event_analytics(db, session_id.strip())
            finally:
                db.close()

        # In-memory fallback (original logic)
        events = self._filter(session_id)
        total_minutes = sum(self._duration_minutes(event) for event in events)
        # Only count real resource events (not node_progress which also has resourceId)
        _RESOURCE_EVENT_TYPES = {"resource_view", "resource_complete", "quiz_result", "quiz_submit", "feedback"}
        resource_events = [
            event for event in events
            if event.get("resourceId") and event.get("event") in _RESOURCE_EVENT_TYPES
        ]
        from collections import Counter
        resource_counter: Counter[str] = Counter(str(event.get("resourceId")) for event in resource_events)
        event_counter: Counter[str] = Counter(str(event.get("event", "unknown")) for event in events)
        # Capture the most recent title for each resourceId from event metadata
        resource_titles: dict[str, str] = {}
        for event in resource_events:
            rid = str(event.get("resourceId", ""))
            if rid and isinstance(event.get("metadata"), dict):
                title = event["metadata"].get("title")
                if title:
                    resource_titles[rid] = str(title)

        quiz_events = [
            event
            for event in events
            if event.get("event") in {"quiz_submit", "quiz_result", "practice_result"}
        ]
        quiz_accuracy = self._quiz_accuracy(quiz_events)

        weak_topics = self._weak_topics(events)
        recommendations = self._recommendations(total_minutes, quiz_accuracy, weak_topics)

        return {
            "eventCount": len(events),
            "totalStudyMinutes": total_minutes,
            "activeResourceCount": len(resource_counter),
            "eventBreakdown": dict(event_counter),
            "topResources": [
                {"resourceId": resource_id, "count": count, "title": resource_titles.get(resource_id, "")}
                for resource_id, count in resource_counter.most_common(5)
            ],
            "quizAccuracy": quiz_accuracy,
            "weakTopics": weak_topics,
            "recommendations": recommendations,
            "recentEvents": events[-10:],
        }

    def reset(self, session_id: str | None = None) -> None:
        if session_id is None:
            self._events.clear()
            return
        sid = session_id.strip()
        if not sid:
            return
        if self._db_enabled:
            try:
                db = self._db_session()
                delete_session(db, sid)
            finally:
                db.close()
        self._events = [event for event in self._events if event.get("sessionId") != sid]

    # ── Internal helpers ──────────────────────────────────────────────

    def _filter(self, session_id: str | None = None) -> list[dict[str, Any]]:
        if session_id is None:
            return []
        sid = session_id.strip()
        if not sid:
            return []
        return [event for event in self._events if event.get("sessionId") == sid]

    def _duration_minutes(self, event: dict[str, Any]) -> int:
        value = event.get("duration") or event.get("durationMinutes") or 0
        try:
            return max(0, int(value))
        except (TypeError, ValueError):
            return 0

    def _quiz_accuracy(self, events: list[dict[str, Any]]) -> int | None:
        if not events:
            return None

        correct = 0
        total = 0
        scores: list[float] = []
        for event in events:
            metadata = event.get("metadata") if isinstance(event.get("metadata"), dict) else {}
            if "accuracy" in metadata:
                try:
                    scores.append(float(metadata["accuracy"]))
                except (TypeError, ValueError):
                    pass
            if "score" in metadata:
                try:
                    scores.append(float(metadata["score"]))
                except (TypeError, ValueError):
                    pass
            if "correct" in metadata and "total" in metadata:
                try:
                    correct += int(metadata["correct"])
                    total += int(metadata["total"])
                except (TypeError, ValueError):
                    pass

        if total > 0:
            return round(correct / total * 100)
        if scores:
            normalized = [score * 100 if score <= 1 else score for score in scores]
            return round(sum(normalized) / len(normalized))
        return None

    def _weak_topics(self, events: list[dict[str, Any]]) -> list[dict[str, Any]]:
        from collections import defaultdict
        topic_stats: dict[str, dict[str, int]] = defaultdict(lambda: {"wrong": 0, "total": 0})
        topic_sources: dict[str, set[str]] = defaultdict(set)
        for event in events:
            metadata = event.get("metadata") if isinstance(event.get("metadata"), dict) else {}
            topic = metadata.get("topic") or metadata.get("knowledgePoint")
            if not topic:
                continue
            topic_key = str(topic)
            stat = topic_stats[topic_key]
            stat["total"] += int(metadata.get("total", 1) or 1)
            stat["wrong"] += int(metadata.get("wrong", 0) or 0)

            # 记录来源
            evt_type = event.get("event", "")
            if evt_type in ("quiz_result", "quiz_submit"):
                topic_sources[topic_key].add("quiz")
            elif evt_type == "practice_result":
                topic_sources[topic_key].add("practice")
            elif evt_type == "feedback":
                topic_sources[topic_key].add("feedback")

        ranked = sorted(
            topic_stats.items(),
            key=lambda item: (item[1]["wrong"] / max(1, item[1]["total"]), item[1]["wrong"]),
            reverse=True,
        )
        return [
            {
                "topic": topic,
                "wrongCount": stat["wrong"],
                "totalCount": stat["total"],
                "risk": round(stat["wrong"] / max(1, stat["total"]), 2),
                "source": sorted(topic_sources.get(topic, ["diagnosis"])),
                "priority": "high" if stat["wrong"] / max(1, stat["total"]) > 0.5 else "medium",
            }
            for topic, stat in ranked[:5]
            if stat["wrong"] > 0
        ]

    def _recommendations(
        self,
        total_minutes: int,
        quiz_accuracy: int | None,
        weak_topics: list[dict[str, Any]],
    ) -> list[str]:
        recommendations: list[str] = []
        if total_minutes < 30:
            recommendations.append("学习时长还偏少，建议先完成一个核心讲义和一组基础练习。")
        if quiz_accuracy is not None and quiz_accuracy < 70:
            recommendations.append("练习正确率偏低，建议降低资源难度并增加图解讲解。")
        if weak_topics:
            recommendations.append(f"优先复习薄弱知识点：{weak_topics[0]['topic']}。")
        if not recommendations:
            recommendations.append("当前学习节奏稳定，可以继续推进下一阶段任务。")
        return recommendations


learning_tracker = LearningTracker()
