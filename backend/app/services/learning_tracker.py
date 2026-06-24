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

    @staticmethod
    def _require_session_id(
        session_id: str | None,
        event: dict[str, Any] | None = None,
    ) -> str:
        sid = str(session_id or (event or {}).get("sessionId") or "").strip()
        if not sid:
            raise MissingSessionIdError()
        return sid

    # ── Deduplication ────────────────────────────────────────────────

    def _is_duplicate_event(self, event: dict[str, Any], session_id: str) -> bool:
        """Check if an event is a duplicate that should be silently skipped.

        Mirrors the DB-level dedup logic in repository.py so in-memory
        and DB-backed modes behave consistently.

        Dedup policy:

        - ``resource_complete``: idempotent — only first completion per
          (session, resource) is stored.
        - ``resource_view``: time-window dedup — duplicates within
          ``event_dedup_view_window_seconds`` are dropped.
        - All other event types: never deduped.
        """
        event_type = event.get("event", "")
        resource_id = event.get("resourceId")
        if not resource_id:
            return False

        if event_type == "resource_complete":
            return any(
                e.get("event") == "resource_complete"
                and e.get("resourceId") == resource_id
                and e.get("sessionId") == session_id
                for e in self._events
            )

        if event_type == "resource_view":
            from app.config import settings
            window = settings.event_dedup_view_window_seconds
            cutoff = time.time() - window
            return any(
                e.get("event") == "resource_view"
                and e.get("resourceId") == resource_id
                and e.get("sessionId") == session_id
                and e.get("timestamp", 0) >= cutoff
                for e in self._events
            )

        return False

    # ── Public API ────────────────────────────────────────────────────

    def log(self, event: dict[str, Any], session_id: str | None = None) -> dict[str, Any]:
        sid = self._require_session_id(session_id, event)
        normalized = {
            **event,
            "sessionId": sid,
            "timestamp": event.get("timestamp") or time.time(),
        }

        # ── Deduplication check ───────────────────────────────────
        if self._is_duplicate_event(event, sid):
            logger.debug(
                "Dedup: skipped %s event for session=%s resource=%s",
                event.get("event", "?"), sid, event.get("resourceId", "?"),
            )
            return normalized

        if self._db_enabled:
            try:
                db = self._db_session()
                result = log_event(
                    db,
                    session_id=normalized["sessionId"],
                    event_type=str(event.get("event", "generic")),
                    resource_id=event.get("resourceId"),
                    metadata=event.get("metadata", event),
                )
                # If log_event returned None (DB-side duplicate), do not
                # add to in-memory either — keep both stores in sync.
                if result is None:
                    return normalized
            finally:
                db.close()

        # Always keep in-memory cache for backward compat
        self._events.append(normalized)
        return normalized

    def recent(self, session_id: str | None = None, limit: int = 10) -> list[dict[str, Any]]:
        sid = self._require_session_id(session_id)
        if self._db_enabled:
            try:
                db = self._db_session()
                events = get_events(db, sid, limit=limit)
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

        filtered = self._filter(sid)
        return filtered[-limit:]

    def summary(self, session_id: str | None = None) -> dict[str, Any]:
        sid = self._require_session_id(session_id)
        if self._db_enabled:
            try:
                db = self._db_session()
                return get_event_analytics(db, sid)
            finally:
                db.close()

        # In-memory fallback (original logic)
        events = self._filter(sid)
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

        # Quiz latest/best tracking
        quiz_results: list[dict[str, Any]] = []
        for event in quiz_events:
            metadata = event.get("metadata") if isinstance(event.get("metadata"), dict) else {}
            pct: float | None = None
            if "accuracy" in metadata:
                try:
                    a = float(metadata["accuracy"])
                    pct = round(a * 100) if a <= 1 else round(a)
                except (TypeError, ValueError):
                    pass
            if pct is None and "score" in metadata:
                try:
                    s = float(metadata["score"])
                    pct = round(s * 100) if s <= 1 else round(s)
                except (TypeError, ValueError):
                    pass
            if pct is None and "correct" in metadata and "total" in metadata:
                try:
                    c = int(metadata["correct"])
                    t = int(metadata["total"])
                    if t > 0:
                        pct = round(c / t * 100)
                except (TypeError, ValueError):
                    pass
            if pct is not None:
                quiz_results.append({
                    "score": pct,
                    "topic": metadata.get("topic") or metadata.get("knowledgePoint") or "",
                    "timestamp": event.get("timestamp", 0),
                })

        latest_quiz_score: dict[str, Any] | None = None
        best_quiz_score: dict[str, Any] | None = None
        if quiz_results:
            latest_quiz_score = quiz_results[-1]
            best_quiz_score = max(quiz_results, key=lambda r: r["score"])
            latest_quiz_score["source"] = "analytics"
            latest_quiz_score["quality_status"] = "computed"
            best_quiz_score["source"] = "analytics"
            best_quiz_score["quality_status"] = "computed"

        # Feedback explainable stats
        feedback_events = [e for e in events if e.get("event") == "feedback"]
        feedback_ratings: list[int] = []
        for fe in feedback_events:
            meta = fe.get("metadata") if isinstance(fe.get("metadata"), dict) else {}
            rating = meta.get("rating")
            if rating is not None:
                try:
                    feedback_ratings.append(int(rating))
                except (TypeError, ValueError):
                    pass
        feedback_stats: dict[str, Any] | None = None
        if feedback_events:
            avg_rating = round(sum(feedback_ratings) / len(feedback_ratings), 1) if feedback_ratings else None
            feedback_stats = {
                "count": len(feedback_events),
                "averageRating": avg_rating,
                "source": "analytics",
                "quality_status": "computed",
                "evidence": f"{len(feedback_events)} feedback event(s) with {len(feedback_ratings)} rating(s)",
            }

        return {
            "eventCount": len(events),
            "totalStudyMinutes": total_minutes,
            "activeResourceCount": len(resource_counter),
            # completedResources counts unique (session, resource) completions
            # because resource_complete events are deduped at log time.
            "viewedResources": event_counter.get("resource_view", 0),
            "completedResources": event_counter.get("resource_complete", 0),
            "practiceCount": event_counter.get("practice_result", 0),
            "eventBreakdown": dict(event_counter),
            "topResources": [
                {"resourceId": resource_id, "count": count, "title": resource_titles.get(resource_id, "")}
                for resource_id, count in resource_counter.most_common(5)
            ],
            "quizAccuracy": quiz_accuracy,
            "weakTopics": weak_topics,
            "recommendations": recommendations,
            "latestQuizScore": latest_quiz_score,
            "bestQuizScore": best_quiz_score,
            "feedbackStats": feedback_stats,
            "recentEvents": list(reversed(events[-10:])),
        }

    def reset(self, session_id: str | None = None) -> None:
        if session_id is None:
            self._events.clear()
            return
        sid = self._require_session_id(session_id)
        if self._db_enabled:
            try:
                db = self._db_session()
                delete_session(db, sid)
            finally:
                db.close()
        self._events = [event for event in self._events if event.get("sessionId") != sid]

    # ── Internal helpers ──────────────────────────────────────────────

    def _filter(self, session_id: str | None = None) -> list[dict[str, Any]]:
        sid = self._require_session_id(session_id)
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
    ) -> list[dict[str, Any]]:
        """Generate structured recommendations from in-memory event data.

        Uses the shared recommendation engine.  In-memory mode does not have
        DB access for ResourceModel / LearningPathModel, so resource-backed
        sources (1, 3, 4) produce no output.  Sources 2 & 5 (weak-topic-based)
        still generate actionable recommendations.
        """
        from app.services.recommendation_engine import generate_recommendations

        return generate_recommendations(
            session_id="",
            weak_topics=weak_topics,
            resources=[],
            learning_path=None,
            db=None,
        )


learning_tracker = LearningTracker()
