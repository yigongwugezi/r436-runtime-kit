"""Knowledge Graph API — serves node-edge graph data for G6 visualization.

Knowledge points come from:
1. KnowledgePointModel table (admin-curated DAG)
2. The persisted learning-path structure
3. LLM generation when neither source contains usable structure
"""
from __future__ import annotations

import logging
import time
from typing import Any

from fastapi import APIRouter, Depends

from app.routers.product import (
    _apply_node_progress,
    _ensure_session_linked as _product_ensure_session_linked,
    _resolve_session_id,
    _require_session_learner,
    _normalize_content_status,
    _product_response,
    _safe_mermaid_label,
)
from app.services.agent_service import (
    get_learning_path as ag_get_learning_path,
    get_resources as ag_get_resources,
)
from app.db.repository import CurrentPathUnresolvedError
from app.middleware.auth import AuthContext, require_auth

logger = logging.getLogger("app.knowledge_graph")

router = APIRouter(prefix="/knowledge-graph", tags=["knowledge-graph"])


def _current_path_or_none(session_id: str, subject_id: str) -> dict[str, Any] | None:
    try:
        return ag_get_learning_path(session_id, subject_id)
    except CurrentPathUnresolvedError:
        return None


@router.get("")
def get_knowledge_graph(
    sessionId: str = "",
    subjectId: str = "",
    chapter: str = "",
    auth: AuthContext = Depends(require_auth),
) -> dict[str, Any]:
    """Return the full knowledge graph (nodes + edges) for a session."""
    session_id = _resolve_session_id(sessionId, subjectId)
    subject_id = str(subjectId).strip()
    _require_session_learner(session_id, auth)
    _ensure_session_linked(session_id, subject_id=subject_id, learner_id=auth.learner_id)


    # 1. Get learning path
    path = _current_path_or_none(session_id, subject_id)
    if not path:
        return _empty_graph(session_id, subjectId)

    raw_stages = path.get("stages", [])
    if not raw_stages:
        return _empty_graph(session_id, subjectId)

    stages = _apply_node_progress(_raw_stages_to_nodes(raw_stages), session_id)

    all_nodes: list[dict[str, Any]] = []
    all_edges: list[dict[str, Any]] = []
    seen_kps: set[str] = set()
    chapter_names: list[str] = []
    seen_chapters: set[str] = set()

    # ── 1. Chapter-based knowledge points (PlannerAgent chapter mode) ──
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
                    all_nodes.append({
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
                    })
                    if prev_kp_id and prev_kp_id in seen_kps:
                        all_edges.append({"source": prev_kp_id, "target": kp_id, "relation": "related"})
                    sec_id = sec.get("id", "")
                    if sec_id:
                        all_edges.append({"source": sec_id, "target": kp_id, "relation": "contains"})
                    prev_kp_id = kp_id

    # Prerequisite edges from flat nodes
    for stage in stages:
        for node in stage.get("nodes", []):
            nid = node.get("id", "")
            prereqs = node.get("prerequisites", [])
            if not prereqs or nid not in seen_kps:
                continue
            for prereq in prereqs:
                prereq_id = prereq if isinstance(prereq, str) else prereq.get("id", "")
                if prereq_id and prereq_id in seen_kps:
                    all_edges.append({"source": prereq_id, "target": nid, "relation": "prerequisite"})

    # ── 2. Fallback: no chapter-based KPs → load from DB or LLM ──
    if not all_nodes:
        kp_rows = _load_or_generate_kps(session_id, subject_id, stages)

        for kp in kp_rows:
            kp_id = kp["id"]
            if not kp_id or kp_id in seen_kps:
                continue
            seen_kps.add(kp_id)
            kp_chapter = kp.get("chapter", "")
            if kp_chapter and kp_chapter not in seen_chapters:
                seen_chapters.add(kp_chapter)
                chapter_names.append(kp_chapter)
            all_nodes.append({
                "id": kp_id,
                "label": kp["name"],
                "type": kp.get("type", "concept"),
                "category": kp_chapter,
                "chapter": kp_chapter,
                "mastery": int(kp.get("_mastery", 0)),
                "status": str(kp.get("_status", "not_started")),
                "difficulty": kp.get("difficulty", "medium"),
                "importance": min(5, max(1, int(kp.get("importance", 3)) // 2)),
                "resourceCount": 0,
                "completedCount": 0,
            })

        # Build edges with dedup: same (source,target) → keep highest priority
        edge_map: dict[tuple[str, str], str] = {}  # (source,target) → relation
        _priority = {"prerequisite": 0, "contains": 1, "related": 2}
        for kp in kp_rows:
            kp_id = kp["id"]
            for prereq_id in kp.get("prerequisites", []):
                if isinstance(prereq_id, str) and prereq_id in seen_kps:
                    key = (prereq_id, kp_id)
                    if key not in edge_map or _priority.get("prerequisite", 9) < _priority.get(edge_map[key], 9):
                        edge_map[key] = "prerequisite"
            for rel_id in kp.get("related", []):
                if isinstance(rel_id, str) and rel_id in seen_kps:
                    key = (kp_id, rel_id)
                    if key not in edge_map or _priority.get("related", 9) < _priority.get(edge_map[key], 9):
                        edge_map[key] = "related"
            part_of_id = kp.get("part_of", "")
            if part_of_id and isinstance(part_of_id, str) and part_of_id in seen_kps:
                key = (part_of_id, kp_id)
                if key not in edge_map or _priority.get("contains", 9) < _priority.get(edge_map[key], 9):
                    edge_map[key] = "contains"
        for (src, tgt), rel in edge_map.items():
            all_edges.append({"source": src, "target": tgt, "relation": rel})

    # ── 3. Enrich with resource counts ──
    try:
        resources = ag_get_resources(session_id)
        kp_to_resource: dict[str, list[dict]] = {}
        for r in resources:
            for kp_ref in (r.get("knowledge_points") or []):
                if kp_ref in seen_kps:
                    kp_to_resource.setdefault(kp_ref, []).append(r)
        for node in all_nodes:
            related = kp_to_resource.get(node["id"], [])
            node["resourceCount"] = len(related)
            node["completedCount"] = sum(1 for r in related if r.get("study_status") == "completed")
    except Exception:
        logger.warning("Failed to enrich node resource counts", exc_info=True)

    if chapter:
        all_nodes = [n for n in all_nodes if n["chapter"] == chapter]
        chapter_node_ids = {n["id"] for n in all_nodes}
        all_edges = [e for e in all_edges if e["source"] in chapter_node_ids and e["target"] in chapter_node_ids]

    mastered_count = sum(1 for n in all_nodes if n["status"] == "mastered")
    meta = {
        "totalNodes": len(all_nodes), "totalEdges": len(all_edges),
        "masteredCount": mastered_count, "chapters": chapter_names, "source": "agent_generated",
    }
    return _product_response(
        {"nodes": all_nodes, "edges": all_edges, "meta": meta},
        session_id=session_id, subject_id=subjectId, source="agent_generated",
    )


@router.get("/nodes/{node_id}")
def get_node_detail(
    node_id: str, sessionId: str = "", subjectId: str = "",
    auth: AuthContext = Depends(require_auth),
) -> dict[str, Any]:
    """Return detailed info for a single knowledge node."""
    session_id = _resolve_session_id(sessionId, subjectId)
    _require_session_learner(session_id, auth)
    _ensure_session_linked(session_id, subject_id=str(subjectId).strip(), learner_id=auth.learner_id)

    # Find node in learning path
    path = _current_path_or_none(session_id, str(subjectId).strip())
    node_info: dict[str, Any] | None = None
    linked_sections: list[dict] = []
    prerequisites: list[dict] = []
    dependents: list[dict] = []

    if path:
        raw_stages = path.get("stages", [])
        stages = _apply_node_progress(_raw_stages_to_nodes(raw_stages), session_id)
        all_kp_ids: set[str] = set()

        # Chapter-based lookup
        for stage in stages:
            for ch in stage.get("chapters", []):
                for sec in ch.get("sections", []):
                    for kp in sec.get("knowledgePoints", []):
                        kp_id = kp.get("id", "")
                        all_kp_ids.add(kp_id)
                        if kp_id == node_id:
                            node_info = {
                                "id": kp_id, "label": kp.get("name", kp_id),
                                "description": kp.get("description", ""),
                                "type": kp.get("type", "concept"),
                                "mastery": kp.get("mastery", 0),
                                "status": kp.get("status", "not_started"),
                                "difficulty": kp.get("difficulty", "medium"),
                                "importance": _calc_importance(kp),
                                "category": ch.get("title", ""),
                            }

        # DB / LLM-generated KP lookup
        if not node_info:
            kp_rows = _load_or_generate_kps(session_id, subject_id, stages)
            kp_by_id = {kp["id"]: kp for kp in kp_rows}
            target = kp_by_id.get(node_id)
            if target:
                node_info = {
                    "id": target["id"], "label": target["name"],
                    "description": target.get("description", ""),
                    "type": target.get("type", "concept"),
                    "mastery": int(target.get("_mastery", 0)),
                    "status": str(target.get("_status", "not_started")),
                    "difficulty": target.get("difficulty", "medium"),
                    "importance": min(5, max(1, int(target.get("importance", 3)) // 2)),
                    "category": target.get("chapter", ""),
                }
                for pid in target.get("prerequisites", []):
                    if pid in kp_by_id:
                        prerequisites.append({"id": pid, "label": kp_by_id[pid]["name"], "relation": "prerequisite"})
                for rid in target.get("related", []):
                    if rid in kp_by_id:
                        prerequisites.append({"id": rid, "label": kp_by_id[rid]["name"], "relation": "related"})
                part_of_id = target.get("part_of", "")
                if part_of_id and part_of_id in kp_by_id:
                    node_info["parent"] = {"id": part_of_id, "label": kp_by_id[part_of_id]["name"]}
                for kp_id, kp in kp_by_id.items():
                    if node_id in kp.get("prerequisites", []):
                        dependents.append({"id": kp_id, "label": kp["name"], "relation": "prerequisite"})
                    if node_id in kp.get("related", []):
                        dependents.append({"id": kp_id, "label": kp["name"], "relation": "related"})
                    if kp.get("part_of", "") == node_id:
                        dependents.append({"id": kp_id, "label": kp["name"], "relation": "child"})

    if not node_info:
        return _product_response({"error": "Node not found", "nodeId": node_id}, session_id=session_id, source="none")

    resources: list[dict] = []
    try:
        for r in ag_get_resources(session_id):
            if node_id in (r.get("knowledge_points") or []):
                resources.append({
                    "id": r.get("id", ""), "title": r.get("title", ""),
                    "type": r.get("type", "resource"),
                    "studyStatus": r.get("study_status", "not_started"),
                })
    except Exception:
        pass

    node_info["resources"] = resources
    node_info["linkedSections"] = linked_sections
    node_info["prerequisites"] = prerequisites
    node_info["dependents"] = dependents
    return _product_response(node_info, session_id=session_id, source="agent_generated")


# ── Core: load KPs from DB, or generate via LLM ────────────────────────

def _load_or_generate_kps(session_id: str, subject_id: str, stages: list) -> list[dict[str, Any]]:
    """Load knowledge points from DB/path, or generate via LLM as a last resort."""
    kp_rows: list[dict[str, Any]] = []

    # Resolve subject
    resolved_subject = subject_id
    if not resolved_subject and session_id:
        try:
            from app.db.engine import SessionLocal
            from app.db.models import SessionModel
            db = SessionLocal()
            sess = db.get(SessionModel, session_id)
            if sess and sess.subject_id:
                resolved_subject = str(sess.subject_id)
            db.close()
        except Exception:
            pass

    # Resolve course name (needed for cache key to avoid cross-course pollution)
    course_name, course_desc = _resolve_course_context(session_id, subject_id)
    if not course_name:
        path = ag_get_learning_path(session_id)
        course_name = str(path.get("course_name", "") or "").strip() if path else ""

    # 1. Try DB KnowledgePointModel — filter by subject + course_name
    if course_name:
        try:
            from app.db.engine import SessionLocal
            from app.db.models import KnowledgePointModel
            db = SessionLocal()
            q = db.query(KnowledgePointModel)
            if resolved_subject:
                q = q.filter(KnowledgePointModel.subject == resolved_subject)
            q = q.filter(KnowledgePointModel.chapter == course_name)
            for r in q.all():
                meta = r.metadata_ or {}
                kp_rows.append({
                    "id": r.id, "name": r.name, "type": "concept",
                    "description": r.description or "",
                    "prerequisites": list(r.prerequisites or []),
                    "related": list(meta.get("related", [])),
                    "part_of": str(meta.get("part_of", "")),
                    "difficulty": r.difficulty or "medium",
                    "importance": r.importance or 5, "chapter": r.chapter or "",
                    "_mastery": 0, "_status": "not_started",
                })
            db.close()
            if kp_rows:
                return kp_rows
        except Exception:
            logger.warning("Failed to load KnowledgePointModel", exc_info=True)

    # 2. A GET must remain useful when the configured LLM is unavailable.
    path_rows = _path_kps(stages)
    if path_rows:
        return path_rows

    # 3. Generate via LLM only when the persisted path has no usable structure.
    if course_name:
        generated = _generate_kps_via_llm(course_name, course_desc, stages)
        if generated:
            _save_kps_to_db(generated, resolved_subject or subject_id or course_name, course_name)
            return generated

    return []


def _path_kps(stages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Build a stable graph from canonical stage/task IDs without external calls."""
    rows: list[dict[str, Any]] = []
    previous_stage_id = ""
    for stage_index, stage in enumerate(stages):
        if not isinstance(stage, dict):
            continue
        stage_id = str(stage.get("id") or stage.get("stage_id") or f"stage_{stage_index}")
        stage_title = str(stage.get("title") or f"阶段 {stage_index + 1}").strip()
        tasks = [task for task in stage.get("tasks", []) if isinstance(task, dict)]
        stage_status = {
            "completed": "mastered", "current": "in_progress", "locked": "blocked",
        }.get(str(stage.get("progressStatus") or ""), "not_started")
        completed = sum(_normalize_content_status(task.get("status", "")) == "mastered" for task in tasks)
        rows.append({
            "id": stage_id, "name": stage_title, "type": "concept",
            "description": str(stage.get("objective") or stage.get("description") or ""),
            "prerequisites": [previous_stage_id] if previous_stage_id else [],
            "related": [], "part_of": "", "difficulty": "medium", "importance": 8,
            "chapter": stage_title,
            "_mastery": round(completed / len(tasks) * 100) if tasks else 0,
            "_status": stage_status,
        })

        previous_task_id = ""
        for task_index, task in enumerate(tasks):
            task_id = str(task.get("task_id") or task.get("id") or f"{stage_id}_task_{task_index}")
            title = str(task.get("title") or stage_title).strip()
            for separator in ("：", ":"):
                if separator in title:
                    title = title.split(separator, 1)[1].strip() or title
                    break
            task_type = str(task.get("type") or "").lower()
            kp_type = "memory" if "review" in task_type else (
                "procedure" if any(token in task_type for token in ("quiz", "practice", "hands", "code")) else "concept"
            )
            status = _normalize_content_status(task.get("status", ""))
            rows.append({
                "id": task_id, "name": title, "type": kp_type,
                "description": str(task.get("goal") or ""),
                "prerequisites": [previous_task_id] if previous_task_id else [],
                "related": [], "part_of": stage_id,
                "difficulty": str(task.get("difficulty") or "medium"), "importance": 5,
                "chapter": stage_title,
                "_mastery": 100 if status == "mastered" else int(task.get("mastery") or 0),
                "_status": status,
            })
            previous_task_id = task_id
        previous_stage_id = stage_id
    return rows


# ── Course context ──────────────────────────────────────────────────────

def _resolve_course_context(session_id: str, subject_id: str) -> tuple[str, str]:
    """Get course name and description from session profile."""
    try:
        from app.services.conversation_state import conversation_store
        from app.services.course_catalog import course_catalog
        state = conversation_store.get(session_id)
        facts = state.facts if state else {}
        topic = str(facts.get("target_course", "")).strip()
        desc_parts = []
        for key, label in [("learning_goal", "学习目标"), ("background", "学生基础"), ("knowledge_base", "已有知识")]:
            val = str(facts.get(key, "")).strip()
            if val:
                desc_parts.append(f"{label}：{val}")
        if not topic and subject_id:
            course = course_catalog.get_course(subject_id)
            if course:
                topic = str(course.get("course_name", ""))
                cd = str(course.get("description", ""))
                if cd:
                    desc_parts.append(cd)
        return topic, "；".join(desc_parts)
    except Exception:
        return "", ""


# ── LLM generation ─────────────────────────────────────────────────────

def _generate_kps_via_llm(course_name: str, course_desc: str, stages: list) -> list[dict[str, Any]] | None:
    """Generate knowledge points via LLM + web search + RAG knowledge base."""
    try:
        from app.services.llm_factory import get_chat_client
        llm = get_chat_client()
    except Exception:
        logger.warning("LLM unavailable for KP generation")
        return None

    # Collect context
    context_parts = [f"课程/主题：{course_name}"]
    if course_desc:
        context_parts.append(f"【课程描述/学习背景】\n{course_desc}")

    # Web search
    try:
        from app.services.search_client import get_search_client
        search = get_search_client("duckduckgo")
        resp = search.search(f"{course_name} 课程大纲 核心知识点 知识结构", max_results=5)
        if resp and resp.results:
            snippets = []
            for r in resp.results[:5]:
                title = (r.title or "").strip()
                snippet = (r.snippet or "").strip()
                if title or snippet:
                    snippets.append(f"- {title}: {snippet}" if title and snippet else (title or snippet))
            if snippets:
                context_parts.append("【联网搜索结果】\n" + "\n".join(snippets))
    except Exception:
        logger.debug("Web search failed for KP generation", exc_info=True)

    # RAG
    try:
        from app.rag.query_engine import rag_query_engine
        if rag_query_engine.is_ready():
            resp = rag_query_engine.search(course_name, top_k=5)
            if resp and resp.results:
                texts = []
                for r in resp.results[:5]:
                    title = (r.title or "").strip()
                    text = (r.text or "")[:500].strip()
                    if title or text:
                        texts.append(f"## {title}\n{text}" if title else text)
                if texts:
                    context_parts.append("【知识库检索结果】\n" + "\n\n".join(texts))
    except Exception:
        logger.debug("RAG retrieval failed", exc_info=True)

    # LLM prompt
    prompt = (
        "你是一位资深课程设计专家。请根据以下参考资料，为课程提炼出 20-40 个细粒度知识点，"
        "覆盖该课程的全部核心内容，并分析它们之间的关系。\n\n"
        "粒度要求：每个知识点应是一个可独立教学和考核的原子单元，而不是大章节标题。\n"
        "例如不要写「监督学习」，而要拆成「线性回归」「逻辑回归」「决策树」「SVM」等。\n\n"
        + "\n\n".join(context_parts)
        + "\n\n"
        "【输出要求】\n"
        "严格按照以下 JSON 数组格式输出，不要包含 Markdown 包裹或额外说明：\n"
        '[\n'
        '  {\n'
        '    "name": "知识点名称（简洁准确的原子知识点，如：梯度下降、SVM核技巧）",\n'
        '    "type": "concept（概念理论） / procedure（方法技能） / memory（事实记忆）",\n'
        '    "difficulty": "easy / medium / hard",\n'
        '    "description": "一句话描述该知识点的核心内容",\n'
        '    "prerequisites": ["前置依赖：必须先学的知识点名称，无则为空数组"],\n'
        '    "related": ["关联知识点：无先后顺序但紧密相关的知识点名称"],\n'
        '    "part_of": "所属上级主题名称（如ID3算法属于决策树），无则留空字符串"\n'
        '  }\n'
        ']\n\n'
        "注意：prerequisites/related 中的名称必须和上面定义的 name 完全一致。"
        "part_of 也必须是其他某个知识点的 name。知识点按学习逻辑顺序排列。"
        "数量不少于20个，不足时请基于你的专业知识补充。"
    )

    try:
        raw = llm.chat(messages=[{"role": "user", "content": prompt}], temperature=0.3, max_tokens=6000)
    except Exception:
        logger.warning("LLM call failed for KP generation", exc_info=True)
        return None

    # Parse
    try:
        import json
        s, e = raw.find("["), raw.rfind("]") + 1
        if s < 0 or e <= s:
            return None
        parsed = json.loads(raw[s:e])
        if not isinstance(parsed, list) or len(parsed) == 0:
            return None
    except Exception:
        logger.warning("Failed to parse LLM KP output", exc_info=True)
        return None

    # Build rows
    kp_rows: list[dict[str, Any]] = []
    name_to_id: dict[str, str] = {}
    for i, kp in enumerate(parsed):
        if not isinstance(kp, dict):
            continue
        name = str(kp.get("name", "")).strip()
        if not name:
            continue
        kp_id = f"kp_gen_{i:03d}"
        name_to_id[name] = kp_id
        kp_rows.append({
            "id": kp_id, "name": name,
            "type": str(kp.get("type", "concept")),
            "description": str(kp.get("description", "")),
            "prerequisites": [],
            "related": [],
            "part_of": str(kp.get("part_of", "")).strip(),
            "difficulty": str(kp.get("difficulty", "medium")),
            "importance": _kp_type_importance(str(kp.get("type", "concept")), str(kp.get("description", ""))),
            "chapter": "", "_mastery": 0, "_status": "not_started",
        })

    for i, kp in enumerate(parsed):
        if not isinstance(kp, dict):
            continue
        # Resolve prerequisites
        for pn in (kp.get("prerequisites", []) if isinstance(kp.get("prerequisites"), list) else []):
            pid = name_to_id.get(str(pn).strip())
            if pid and pid != kp_rows[i]["id"]:
                kp_rows[i]["prerequisites"].append(pid)
        # Resolve related
        for rn in (kp.get("related", []) if isinstance(kp.get("related"), list) else []):
            rid = name_to_id.get(str(rn).strip())
            if rid and rid != kp_rows[i]["id"]:
                kp_rows[i]["related"].append(rid)
        # Resolve part_of
        parent_name = str(kp.get("part_of", "")).strip()
        if parent_name:
            pid = name_to_id.get(parent_name)
            if pid and pid != kp_rows[i]["id"]:
                kp_rows[i]["part_of"] = pid
            else:
                kp_rows[i]["part_of"] = ""

    return kp_rows


def _kp_type_importance(kp_type: str, description: str) -> int:
    base = {"concept": 6, "procedure": 5, "memory": 3}.get(kp_type, 4)
    desc = (description or "").lower()
    if any(w in desc for w in ("重点", "核心", "关键", "基础", "重要", "fundamental", "core", "key")):
        base = min(10, base + 2)
    return base


def _save_kps_to_db(kp_rows: list[dict[str, Any]], subject: str, course_name: str = "") -> None:
    if not kp_rows or not subject:
        return
    try:
        from app.db.engine import SessionLocal
        from app.db.models import KnowledgePointModel
        db = SessionLocal()
        existing = {r.id for r in db.query(KnowledgePointModel.id).filter(
            KnowledgePointModel.subject == subject,
            KnowledgePointModel.chapter == course_name,
        ).all()}
        saved = 0
        for kp in kp_rows:
            kp_id = kp["id"]
            if kp_id in existing:
                continue
            db.merge(KnowledgePointModel(
                id=kp_id, subject=subject, name=kp["name"],
                description=kp.get("description", ""),
                prerequisites=kp.get("prerequisites", []),
                difficulty=kp.get("difficulty", "medium"),
                importance=kp.get("importance", 5),
                chapter=course_name or kp.get("chapter", ""),
                metadata_={"related": kp.get("related", []), "part_of": kp.get("part_of", "")},
            ))
            saved += 1
        if saved:
            db.commit()
            logger.info("Saved %d generated KPs to DB for subject=%s", saved, subject)
        db.close()
    except Exception:
        logger.warning("Failed to persist generated KPs to DB", exc_info=True)


# ── Helpers ──────────────────────────────────────────────────────────

def _empty_graph(session_id: str, subjectId: str) -> dict[str, Any]:
    return _product_response(
        {"nodes": [], "edges": [], "meta": {"totalNodes": 0, "totalEdges": 0, "masteredCount": 0, "chapters": []}},
        session_id=session_id, subject_id=subjectId, source="none",
    )


def _ensure_session_linked(session_id: str, subject_id: str = "", learner_id: str = "") -> None:
    _product_ensure_session_linked(session_id, subject_id=subject_id, learner_id=learner_id)


def _raw_stages_to_nodes(stages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    from app.routers.product import _raw_stages_to_nodes as _r
    return _r(stages)


def _calc_importance(kp: dict) -> int:
    type_map = {"concept": 4, "procedure": 3, "memory": 2}
    base = type_map.get(kp.get("type", ""), 2)
    desc = (kp.get("description", "") or "").lower()
    if any(w in desc for w in ("重点", "核心", "关键", "important", "key")):
        base = min(5, base + 1)
    return base
