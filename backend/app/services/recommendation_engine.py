"""Structured recommendation engine for Learning Analytics.

Generates recommendations from 5 data sources:
1. Incomplete resources (study_status != 'completed')
2. Low quiz-accuracy knowledge points (from weakTopics, matched to resources)
3. Incomplete practice resources (type/format indicating practice, not completed)
4. Current stage incomplete (from LearningPathModel.stages)
5. High-frequency weak topics (repeated across multiple quiz attempts)

Shared by both the DB path (repository.get_event_analytics) and the in-memory
fallback (learning_tracker.LearningTracker._recommendations).
"""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy.orm import Session

from app.db.models import LearningPathModel, ResourceModel

logger = logging.getLogger(__name__)

# ── Public entry point ──────────────────────────────────────────────────────

RECOMMENDATION_TYPES = frozenset({
    "incomplete_resource",
    "low_accuracy_topic",
    "incomplete_practice",
    "stage_incomplete",
    "frequent_weak_topic",
})


def generate_recommendations(
    *,
    session_id: str,
    weak_topics: list[dict[str, Any]],
    resources: list[ResourceModel] | None = None,
    learning_path: LearningPathModel | None = None,
    db: Session | None = None,
) -> list[dict[str, Any]]:
    """Generate structured recommendations from all available data sources.

    Args:
        session_id: Current session identifier (for logging/scoping).
        weak_topics: Pre-computed weak topic list from analytics.
        resources: Session-scoped ResourceModel list (DB path), or empty/None (in-memory).
        learning_path: Latest LearningPathModel (DB path), or None (in-memory).
        db: Active DB session (for additional lookups if needed).

    Returns:
        List of recommendation dicts matching RecommendationItem schema,
        deduplicated and ranked by priority → confidence. Empty list when
        no actionable data exists.
    """
    if resources is None:
        resources = []

    all_recs: list[dict[str, Any]] = []

    # Source 1: incomplete resources
    all_recs.extend(_source_incomplete_resources(resources))

    # Source 2: low accuracy topics → match to resources
    all_recs.extend(_source_low_accuracy_topics(weak_topics, resources))

    # Source 3: incomplete practice resources
    all_recs.extend(_source_incomplete_practice(resources))

    # Source 4: current stage incomplete
    all_recs.extend(_source_stage_incomplete(learning_path, resources))

    # Source 5: high-frequency weak topics
    all_recs.extend(_source_frequent_weak_topics(weak_topics, resources))

    return _deduplicate_and_rank(all_recs)


# ── Source functions ────────────────────────────────────────────────────────


def _source_incomplete_resources(
    resources: list[ResourceModel],
) -> list[dict[str, Any]]:
    """Source 1: resources with study_status != 'completed'."""
    recs: list[dict[str, Any]] = []
    incomplete = [r for r in resources if r.study_status != "completed"]
    for res in incomplete:
        rtype = (res.type or "").lower()
        fmt = (res.format or "").lower()
        # Priority: quiz/practice > lecture > other
        if rtype in ("quiz", "practice") or fmt in ("quiz", "code"):
            priority = "high"
        elif rtype == "lecture":
            priority = "medium"
        else:
            priority = "low"

        recs.append({
            "recommendation_type": "incomplete_resource",
            "title": f"完成未学完的资源：{res.title}",
            "reason": f"资源「{res.title}」尚未完成学习（状态：{res.study_status}）",
            "target_resource_id": res.id,
            "target_stage_id": res.related_stage_id,
            "priority": priority,
            "source": "db",
            "confidence": 0.9,
            "evidence": (
                f"Resource '{res.id}' of type '{res.type}' has "
                f"study_status='{res.study_status}' in current session"
            ),
            "quality_status": "passed",
        })
    return recs


def _source_low_accuracy_topics(
    weak_topics: list[dict[str, Any]],
    resources: list[ResourceModel],
) -> list[dict[str, Any]]:
    """Source 2: weak topics from quiz results, matched to session resources."""
    recs: list[dict[str, Any]] = []
    for wt in weak_topics:
        topic = str(wt.get("topic", ""))
        if not topic:
            continue
        risk = float(wt.get("risk", 0))
        wrong = int(wt.get("wrongCount", 0))
        total = int(wt.get("totalCount", 0))
        priority = "high" if risk > 0.5 else ("medium" if risk > 0.25 else "low")

        # Find best matching resource in this session
        matched = _find_resource_for_topic(topic, resources)

        recs.append({
            "recommendation_type": "low_accuracy_topic",
            "title": f"复习薄弱知识点：{topic}",
            "reason": f"知识点「{topic}」正确率偏低（{wrong}/{total} 错误），建议重新学习相关资源",
            "target_resource_id": matched.id if matched else None,
            "target_stage_id": matched.related_stage_id if matched else None,
            "priority": priority,
            "source": "analytics",
            "confidence": round(max(0.3, 1.0 - risk), 2),
            "evidence": f"Topic '{topic}': {wrong} wrong out of {total} attempts (risk={risk})",
            "quality_status": "passed",
        })
    return recs


def _source_incomplete_practice(
    resources: list[ResourceModel],
) -> list[dict[str, Any]]:
    """Source 3: practice/code resources not yet completed."""
    recs: list[dict[str, Any]] = []
    for res in resources:
        if res.study_status == "completed":
            continue
        rtype = (res.type or "").lower()
        fmt = (res.format or "").lower()
        is_practice = (
            "practice" in rtype
            or rtype == "code"
            or fmt in ("code", "quiz")
        )
        if not is_practice:
            continue

        priority = "high" if ("practice" in rtype or fmt == "code") else "medium"
        recs.append({
            "recommendation_type": "incomplete_practice",
            "title": f"完成练习：{res.title}",
            "reason": f"练习资源「{res.title}」尚未完成，动手实践有助于巩固知识",
            "target_resource_id": res.id,
            "target_stage_id": res.related_stage_id,
            "priority": priority,
            "source": "db",
            "confidence": 0.85,
            "evidence": (
                f"Practice resource '{res.id}' (type={res.type}, format={res.format}) "
                f"has study_status='{res.study_status}'"
            ),
            "quality_status": "passed",
        })
    return recs


def _source_stage_incomplete(
    learning_path: LearningPathModel | None,
    resources: list[ResourceModel],
) -> list[dict[str, Any]]:
    """Source 4: current stage in learning path not fully completed."""
    recs: list[dict[str, Any]] = []
    current_stage = _determine_current_stage(learning_path)
    if not current_stage:
        return recs

    stage_id = str(current_stage.get("id") or current_stage.get("stage_id") or "")
    stage_title = str(current_stage.get("title", "当前阶段"))

    # Find resources belonging to this stage
    stage_resources = [
        r for r in resources
        if r.related_stage_id == stage_id
    ]
    incomplete = [r for r in stage_resources if r.study_status != "completed"]
    total = len(stage_resources)
    completed_count = total - len(incomplete)
    progress = completed_count / max(1, total)

    priority = "high" if progress < 0.5 else ("medium" if progress < 0.8 else "low")

    if incomplete:
        recs.append({
            "recommendation_type": "stage_incomplete",
            "title": f"完成当前阶段「{stage_title}」的学习",
            "reason": (
                f"当前阶段 {completed_count}/{total} 资源已完成，"
                f"尚有 {len(incomplete)} 个资源待完成"
            ),
            "target_resource_id": incomplete[0].id,
            "target_stage_id": stage_id,
            "priority": priority,
            "source": "db",
            "confidence": 0.75,
            "evidence": (
                f"Stage '{stage_id}': {completed_count}/{total} resources completed "
                f"(progress={progress:.0%})"
            ),
            "quality_status": "passed",
        })
    return recs


def _source_frequent_weak_topics(
    weak_topics: list[dict[str, Any]],
    resources: list[ResourceModel],
) -> list[dict[str, Any]]:
    """Source 5: topics that appear as weak across multiple events."""
    recs: list[dict[str, Any]] = []
    # Frequent = wrongCount >= 3 OR appears multiple times with high risk
    for wt in weak_topics:
        wrong = int(wt.get("wrongCount", 0))
        risk = float(wt.get("risk", 0))
        topic = str(wt.get("topic", ""))
        if not topic:
            continue
        # Must have significant wrong count or high frequency
        if wrong < 3 and risk < 0.5:
            continue

        matched = _find_resource_for_topic(topic, resources)
        priority = "high" if wrong >= 3 and risk > 0.5 else "medium"
        confidence = min(1.0, 0.5 + (wrong * 0.1))

        recs.append({
            "recommendation_type": "frequent_weak_topic",
            "title": f"高频薄弱知识点：{topic}",
            "reason": f"知识点「{topic}」在多次练习中反复出错（{wrong} 次错误），需要重点关注",
            "target_resource_id": matched.id if matched else None,
            "target_stage_id": matched.related_stage_id if matched else None,
            "priority": priority,
            "source": "analytics",
            "confidence": round(confidence, 2),
            "evidence": (
                f"Topic '{topic}': {wrong} wrong answers across multiple attempts "
                f"(risk={risk})"
            ),
            "quality_status": "passed",
        })
    return recs


# ── Helpers ─────────────────────────────────────────────────────────────────


def _find_resource_for_topic(
    topic: str,
    resources: list[ResourceModel],
) -> ResourceModel | None:
    """Find the best resource in the list whose knowledge_points match the topic."""
    if not topic or not resources:
        return None

    topic_lower = topic.lower()
    best: ResourceModel | None = None

    for res in resources:
        kps = res.knowledge_points
        if not kps:
            continue
        if _topic_matches_knowledge_points(topic_lower, kps):
            # Prefer lecture/quiz types for topic review
            if best is None:
                best = res
            elif (res.type or "") in ("lecture", "quiz", "reading"):
                best = res
                break  # Found ideal type
    return best


def _topic_matches_knowledge_points(topic_lower: str, kps: Any) -> bool:
    """Check if any knowledge point in kps matches the given topic (fuzzy)."""
    if isinstance(kps, list):
        for kp in kps:
            if isinstance(kp, str):
                if topic_lower in kp.lower() or kp.lower() in topic_lower:
                    return True
            elif isinstance(kp, dict):
                kp_name = str(kp.get("name") or kp.get("topic") or "").lower()
                if topic_lower in kp_name or kp_name in topic_lower:
                    return True
    elif isinstance(kps, dict):
        # Defensive: treat dict values as potential topic names
        for v in kps.values():
            if isinstance(v, str) and (topic_lower in v.lower() or v.lower() in topic_lower):
                return True
    return False


def _determine_current_stage(
    learning_path: LearningPathModel | None,
) -> dict[str, Any] | None:
    """Find the first non-completed stage in the learning path."""
    if not learning_path:
        return None
    stages = learning_path.stages
    if not isinstance(stages, list) or not stages:
        return None

    for stage in stages:
        if not isinstance(stage, dict):
            continue
        nodes = stage.get("nodes")
        status = stage.get("status", "")
        if status == "completed":
            continue
        if isinstance(nodes, list) and nodes:
            all_completed = all(
                isinstance(n, dict) and n.get("status") in ("completed", "mastered")
                for n in nodes
            )
            if not all_completed:
                return stage
        else:
            # Stage with no nodes or non-list nodes: consider incomplete
            return stage
    return None


def _deduplicate_and_rank(all_recs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Deduplicate by target_resource_id, keeping highest-priority entry.
    Then sort by priority (high→medium→low) → confidence descending. Cap at 15."""
    if not all_recs:
        return []

    priority_score = {"high": 0, "medium": 1, "low": 2}

    # Group by target_resource_id; None-keyed items are kept separate
    by_resource: dict[str, list[dict[str, Any]]] = {}
    unkeyed: list[dict[str, Any]] = []
    for rec in all_recs:
        rid = rec.get("target_resource_id")
        if rid:
            by_resource.setdefault(str(rid), []).append(rec)
        else:
            unkeyed.append(rec)

    deduped: list[dict[str, Any]] = []
    for rid, recs in by_resource.items():
        # Sort: best priority first, then highest confidence
        recs.sort(
            key=lambda r: (
                priority_score.get(str(r.get("priority", "low")), 99),
                -float(r.get("confidence", 0)),
            )
        )
        best = dict(recs[0])
        # Merge evidence from all recs for the same resource
        all_evidence = [str(r.get("evidence", "")) for r in recs if r.get("evidence")]
        if len(all_evidence) > 1:
            best["evidence"] = "; ".join(all_evidence)
        deduped.append(best)

    deduped.extend(unkeyed)

    # Global sort: priority then confidence
    deduped.sort(
        key=lambda r: (
            priority_score.get(str(r.get("priority", "low")), 99),
            -float(r.get("confidence", 0)),
        )
    )
    return deduped[:15]
