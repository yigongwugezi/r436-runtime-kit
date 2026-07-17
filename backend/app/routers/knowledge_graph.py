"""Knowledge Graph API — serves node-edge graph data for G6 visualization.

Builds the knowledge graph from:
- Learning path stages → chapters → sections → knowledge_points
- Node prerequisites for prerequisite edges
- Resource study_status for mastery calculation
"""
from __future__ import annotations

import logging
import time
from typing import Any

from fastapi import APIRouter, Depends

from app.routers.product import (
    _apply_node_progress,
    _resolve_session_id,
    _normalize_content_status,
    _product_response,
    _safe_mermaid_label,
)
from app.services.agent_service import (
    get_learning_path as ag_get_learning_path,
    get_resources as ag_get_resources,
)
from app.middleware.auth import AuthContext, get_auth

logger = logging.getLogger("app.knowledge_graph")

router = APIRouter(prefix="/knowledge-graph", tags=["knowledge-graph"])


@router.get("")
def get_knowledge_graph(
    sessionId: str = "",
    subjectId: str = "",
    chapter: str = "",
    auth: AuthContext = Depends(get_auth),
) -> dict[str, Any]:
    """Return the full knowledge graph (nodes + edges) for a session.

    Optional ``chapter`` param filters to one chapter's sub-graph.
    """
    session_id = _resolve_session_id(sessionId, subjectId)
    subject_id = str(subjectId).strip()
    _ensure_session_linked(session_id, subject_id=subject_id)

    # 1. Get learning path
    path = ag_get_learning_path(session_id)
    if not path:
        return _product_response(
            {"nodes": [], "edges": [], "meta": {"totalNodes": 0, "totalEdges": 0, "masteredCount": 0, "chapters": []}},
            session_id=session_id, subject_id=subjectId, source="none",
        )

    raw_stages = path.get("stages", [])
    if not raw_stages:
        return _product_response(
            {"nodes": [], "edges": [], "meta": {"totalNodes": 0, "totalEdges": 0, "masteredCount": 0, "chapters": []}},
            session_id=session_id, subject_id=subjectId, source="none",
        )

    # 2. Apply progress to get mastery/status
    stages = _apply_node_progress(_raw_stages_to_nodes(raw_stages), session_id)

    # 3. Extract all knowledge points + build edges
    all_nodes: list[dict[str, Any]] = []
    all_edges: list[dict[str, Any]] = []
    seen_kps: set[str] = set()
    chapter_names: list[str] = []
    seen_chapters: set[str] = set()

    for stage in stages:
        for ch in stage.get("chapters", []):
            ch_title = ch.get("title", "")
            if ch_title and ch_title not in seen_chapters:
                seen_chapters.add(ch_title)
                chapter_names.append(ch_title)

            for sec in ch.get("sections", []):
                prev_kp_id = None
                for kp in sec.get("knowledgePoints", []):
                    kp_id = kp.get("id", "")
                    if not kp_id or kp_id in seen_kps:
                        prev_kp_id = kp_id
                        continue
                    seen_kps.add(kp_id)

                    # Add node
                    node: dict[str, Any] = {
                        "id": kp_id,
                        "label": kp.get("name", kp_id),
                        "type": kp.get("type", "concept"),
                        "category": ch_title,
                        "chapter": ch_title,
                        "mastery": kp.get("mastery", 0),
                        "status": kp.get("status", "not_started"),
                        "difficulty": kp.get("difficulty", "medium"),
                        "importance": _calc_importance(kp),
                        "resourceCount": 0,
                        "completedCount": 0,
                    }
                    all_nodes.append(node)

                    # Edge: sequential within same section
                    if prev_kp_id and prev_kp_id in seen_kps:
                        all_edges.append({
                            "source": prev_kp_id,
                            "target": kp_id,
                            "relation": "related",
                        })

                    # Edge: contains (section → kp)
                    sec_id = sec.get("id", "")
                    if sec_id:
                        all_edges.append({
                            "source": sec_id,
                            "target": kp_id,
                            "relation": "contains",
                        })

                    prev_kp_id = kp_id

    # 4. Add prerequisite edges from flat nodes
    for stage in stages:
        for node in stage.get("nodes", []):
            nid = node.get("id", "")
            prereqs = node.get("prerequisites", [])
            if not prereqs or nid not in seen_kps:
                continue
            for prereq in prereqs:
                prereq_id = prereq if isinstance(prereq, str) else prereq.get("id", "")
                if prereq_id and prereq_id in seen_kps:
                    all_edges.append({
                        "source": prereq_id,
                        "target": nid,
                        "relation": "prerequisite",
                    })

    # 5. Enrich with resource counts
    try:
        resources = ag_get_resources(session_id)
        kp_to_resource: dict[str, list[dict]] = {}
        for r in resources:
            kps = r.get("knowledge_points", [])
            if isinstance(kps, list):
                for kp_ref in kps:
                    if kp_ref in seen_kps:
                        kp_to_resource.setdefault(kp_ref, []).append(r)
        for node in all_nodes:
            nid = node["id"]
            related = kp_to_resource.get(nid, [])
            node["resourceCount"] = len(related)
            node["completedCount"] = sum(
                1 for r in related if r.get("study_status") == "completed"
            )
    except Exception:
        logger.warning("Failed to enrich node resource counts", exc_info=True)

    # 6. Filter by chapter if requested
    if chapter:
        all_nodes = [n for n in all_nodes if n["chapter"] == chapter]
        chapter_node_ids = {n["id"] for n in all_nodes}
        all_edges = [
            e for e in all_edges
            if e["source"] in chapter_node_ids and e["target"] in chapter_node_ids
        ]

    # 7. Build meta
    mastered_count = sum(1 for n in all_nodes if n["status"] == "mastered")
    meta = {
        "totalNodes": len(all_nodes),
        "totalEdges": len(all_edges),
        "masteredCount": mastered_count,
        "chapters": chapter_names,
        "source": "agent_generated",
    }

    return _product_response(
        {"nodes": all_nodes, "edges": all_edges, "meta": meta},
        session_id=session_id, subject_id=subjectId, source="agent_generated",
    )


@router.get("/nodes/{node_id}")
def get_node_detail(
    node_id: str,
    sessionId: str = "",
    subjectId: str = "",
    auth: AuthContext = Depends(get_auth),
) -> dict[str, Any]:
    """Return detailed info for a single knowledge node."""
    session_id = _resolve_session_id(sessionId, subjectId)

    # Find node in learning path
    path = ag_get_learning_path(session_id)
    node_info: dict[str, Any] | None = None
    linked_sections: list[dict] = []
    prerequisites: list[dict] = []
    dependents: list[dict] = []

    if path:
        raw_stages = path.get("stages", [])
        stages = _apply_node_progress(_raw_stages_to_nodes(raw_stages), session_id)

        # Find the node and its siblings
        all_kp_ids: set[str] = set()
        for stage in stages:
            for ch in stage.get("chapters", []):
                for sec in ch.get("sections", []):
                    for kp in sec.get("knowledgePoints", []):
                        kp_id = kp.get("id", "")
                        all_kp_ids.add(kp_id)
                        if kp_id == node_id:
                            node_info = {
                                "id": kp_id,
                                "label": kp.get("name", kp_id),
                                "description": kp.get("description", ""),
                                "type": kp.get("type", "concept"),
                                "mastery": kp.get("mastery", 0),
                                "status": kp.get("status", "not_started"),
                                "difficulty": kp.get("difficulty", "medium"),
                                "importance": _calc_importance(kp),
                                "category": ch.get("title", ""),
                            }
                            linked_sections.append({
                                "id": sec.get("id", ""),
                                "title": sec.get("title", ""),
                                "chapterTitle": ch.get("title", ""),
                            })

        # Find prerequisite relationships
        for stage in stages:
            for node in stage.get("nodes", []):
                nid = node.get("id", "")
                prereqs = node.get("prerequisites", [])
                if nid == node_id and prereqs:
                    for prereq in prereqs:
                        pid = prereq if isinstance(prereq, str) else prereq.get("id", "")
                        if pid in all_kp_ids:
                            prerequisites.append({"id": pid, "label": pid})
                if nid != node_id and node_id in prereqs:
                    dependents.append({"id": nid, "label": node.get("topic", nid)})

    if not node_info:
        return _product_response(
            {"error": "Node not found", "nodeId": node_id},
            session_id=session_id, source="none",
        )

    # Get linked resources
    resources: list[dict] = []
    try:
        all_resources = ag_get_resources(session_id)
        for r in all_resources:
            kps = r.get("knowledge_points", [])
            if isinstance(kps, list) and node_id in kps:
                resources.append({
                    "id": r.get("id", ""),
                    "title": r.get("title", ""),
                    "type": r.get("type", "resource"),
                    "studyStatus": r.get("study_status", "not_started"),
                })
    except Exception:
        logger.warning("Failed to load resources for node detail", exc_info=True)

    node_info["resources"] = resources
    node_info["linkedSections"] = linked_sections
    node_info["prerequisites"] = prerequisites
    node_info["dependents"] = dependents

    return _product_response(
        node_info,
        session_id=session_id, source="agent_generated",
    )


# ── Helpers ──────────────────────────────────────────────────────────

def _ensure_session_linked(session_id: str, subject_id: str = "") -> None:
    """Ensure session is linked to a subject (no-op placeholder matching product.py pattern)."""
    try:
        from app.routers.product import _ensure_session_linked as _esl
        _esl(session_id, subject_id=subject_id)
    except Exception:
        pass


def _raw_stages_to_nodes(stages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Re-export from product.py for local use."""
    from app.routers.product import _raw_stages_to_nodes as _r
    return _r(stages)


def _calc_importance(kp: dict) -> int:
    """Calculate node importance (1-5) from KP attributes."""
    type_map = {"concept": 4, "procedure": 3, "memory": 2}
    base = type_map.get(kp.get("type", ""), 2)
    # Boost if described as key point
    desc = (kp.get("description", "") or "").lower()
    if any(w in desc for w in ("重点", "核心", "关键", "important", "key")):
        base = min(5, base + 1)
    return base
