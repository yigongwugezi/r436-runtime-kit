"""
DeepTutor 学习引擎桥接层
=======================
将 DeepTutor 的 learning/policy.py 和 learning/scheduler.py
接入 EduAgent 的 assessment_loop，实现：
  - 下一步学习建议 (next_objective)
  - 间隔重复复习提醒 (get_due_tasks)
  - 掌握度计算 (compute_mastery)

不依赖 DeepTutor 的完整会话上下文，纯函数调用。
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def build_learning_progress(
    session_id: str,
    stages: list[dict],
    diagnosis: dict | None = None,
    analytics: dict | None = None,
) -> Any | None:
    """将 EduAgent 的路径+诊断+分析数据转换为 DeepTutor 的 LearningProgress。

    Returns None 如果 stages 为空或无法转换。
    """
    if not stages:
        return None

    try:
        from deeptutor.learning.models import (
            KnowledgePoint,
            KnowledgeType,
            LearningModule,
            LearningProgress,
        )
    except ImportError:
        logger.warning("DeepTutor learning module not available, skipping engine bridge")
        return None

    # ── 构建 modules & knowledge_points ──
    modules: list[LearningModule] = []
    all_kps: list[KnowledgePoint] = []
    mastery_levels: dict[str, float] = {}

    diagnosis_mastery = (diagnosis or {}).get("mastery_levels", []) or []
    mastery_map: dict[str, float] = {}
    for m in diagnosis_mastery:
        if isinstance(m, dict):
            name = str(m.get("name", ""))
            score = float(m.get("score", 50))
            if name:
                mastery_map[name] = score

    for stage in stages:
        if not isinstance(stage, dict):
            continue
        stage_id = str(stage.get("stage_id", ""))
        stage_title = str(stage.get("title", ""))

        for ch in stage.get("chapters", []):
            if not isinstance(ch, dict):
                continue
            ch_id = str(ch.get("chapter_id", ""))
            kps_for_chapter: list[KnowledgePoint] = []
            for sec in ch.get("sections", []):
                if not isinstance(sec, dict):
                    continue
                for kp in sec.get("knowledge_points", []):
                    if not isinstance(kp, dict):
                        continue
                    kp_name = str(kp.get("name", ""))
                    if not kp_name:
                        continue
                    kp_id = f"{stage_id}_{ch_id}_{kp_name}"[:80]
                    kp_type = _infer_kp_type(kp)

                    knowledge_pt = KnowledgePoint(
                        id=kp_id,
                        name=kp_name,
                        type=kp_type,
                        module_id=stage_id,
                    )
                    kps_for_chapter.append(knowledge_pt)
                    all_kps.append(knowledge_pt)

                    # 映射掌握度
                    score = mastery_map.get(kp_name, 50)
                    mastery_levels[kp_id] = score / 100.0

            if kps_for_chapter:
                modules.append(
                    LearningModule(
                        id=stage_id,
                        name=stage_title,
                        knowledge_points=kps_for_chapter,
                        order=len(modules),
                    )
                )

    if not modules:
        return None

    return LearningProgress(
        book_id=session_id,
        modules=modules,
        mastery_levels=mastery_levels,
    )


def _infer_kp_type(kp: dict) -> Any:
    """从知识点名称推断 DeepTutor KnowledgeType。"""
    name = str(kp.get("name", "")).lower()
    kp_type_str = str(kp.get("type", "")).lower()

    try:
        from deeptutor.learning.models import KnowledgeType
    except ImportError:
        return None

    if kp_type_str in ("memory", "概念"):
        return KnowledgeType.CONCEPT
    if kp_type_str in ("procedure", "算法", "方法"):
        return KnowledgeType.PROCEDURE

    # 名称推断
    memory_keywords = ("背", "记忆", "记住", "定义", "术语", "公式")
    procedure_keywords = ("步骤", "流程", "算法", "方法", "操作", "实现")
    design_keywords = ("设计", "架构", "系统", "模式", "策略")

    if any(k in name for k in memory_keywords):
        return KnowledgeType.MEMORY
    if any(k in name for k in procedure_keywords):
        return KnowledgeType.PROCEDURE
    if any(k in name for k in design_keywords):
        return KnowledgeType.DESIGN

    return KnowledgeType.CONCEPT


def get_next_action(progress: Any) -> dict | None:
    """调用 DeepTutor 的 next_objective()，返回下一步学习建议。

    Returns:
        dict with keys: action, knowledge_point_name, mastery, reason,
        module_name, knowledge_point_type, status, threshold
        Returns None if engine unavailable or path is complete.
    """
    if progress is None:
        return None

    try:
        from deeptutor.learning.policy import next_objective
        from deeptutor.learning.policy import NextStep

        result = next_objective(progress)
        if result is None or result.action == "complete":
            return None

        return {
            "action": result.action,
            "knowledge_point_name": result.knowledge_point_name,
            "mastery": result.mastery,
            "reason": result.reason,
            "module_name": result.module_name,
            "knowledge_point_type": result.knowledge_point_type,
            "status": result.status,
            "threshold": result.threshold,
        }
    except ImportError:
        logger.debug("DeepTutor policy module unavailable")
        return None
    except Exception:
        logger.exception("next_objective() failed")
        return None


def get_due_reviews(progress: Any, max_items: int = 5) -> list[dict]:
    """从 DeepTutor 的间隔重复调度器获取到期复习任务。

    Returns:
        [{"knowledge_point_name": str, "due_at": float, "interval_index": int}, ...]
    """
    if progress is None:
        return []

    try:
        from deeptutor.learning.scheduler import SpacedRepetitionScheduler

        scheduler = SpacedRepetitionScheduler()
        due = scheduler.get_due_tasks(progress, max_tasks=max_items)

        results = []
        for task in due:
            kp = _find_kp_by_id(progress, task.knowledge_point_id)
            results.append({
                "knowledge_point_id": task.knowledge_point_id,
                "knowledge_point_name": kp.name if kp else "",
                "due_at": task.due_at,
                "interval_index": task.interval_index,
                "type": kp.type.value if kp else "",
            })
        return results
    except ImportError:
        logger.debug("DeepTutor scheduler unavailable")
        return []
    except Exception:
        logger.exception("get_due_tasks() failed")
        return []


def _find_kp_by_id(progress: Any, kp_id: str) -> Any:
    """在 progress 的 modules 中根据 id 查找 KnowledgePoint。"""
    for module in progress.modules:
        for kp in module.knowledge_points:
            if kp.id == kp_id:
                return kp
    return None


def get_review_schedule(knowledge_type: str = "concept") -> list[int]:
    """获取某个知识类型的间隔重复序列（天数）。"""
    try:
        from deeptutor.learning.scheduler import INTERVAL_SEQUENCES
        from deeptutor.learning.models import KnowledgeType

        kt_map = {
            "memory": KnowledgeType.MEMORY,
            "concept": KnowledgeType.CONCEPT,
            "procedure": KnowledgeType.PROCEDURE,
            "design": KnowledgeType.DESIGN,
        }
        kt = kt_map.get(knowledge_type.lower(), KnowledgeType.CONCEPT)
        return list(INTERVAL_SEQUENCES.get(kt, [3, 7, 14, 30]))
    except ImportError:
        return [3, 7, 14, 30]


def save_progress(session_id: str, progress: Any) -> bool:
    """持久化 LearningProgress 到 DeepTutor 的存储。

    跨调用保持掌握度、复习状态、答题记录。"""
    if progress is None:
        return False
    try:
        from deeptutor.learning.storage import LearningStore
        from deeptutor.services.path_service import get_path_service
        ps = get_path_service()
        workspace = ps.get_user_workspace("default")
        store = LearningStore(workspace / "learning")
        store.save(session_id, progress)
        return True
    except ImportError:
        logger.debug("DeepTutor storage unavailable, skipping persistence")
        return False
    except Exception:
        logger.exception("Failed to persist LearningProgress for %s", session_id)
        return False


def load_progress(session_id: str) -> Any | None:
    """从 DeepTutor 存储加载 LearningProgress。"""
    try:
        from deeptutor.learning.storage import LearningStore
        from deeptutor.services.path_service import get_path_service
        ps = get_path_service()
        workspace = ps.get_user_workspace("default")
        store = LearningStore(workspace / "learning")
        return store.load(session_id)
    except ImportError:
        return None
    except Exception:
        logger.debug("Failed to load LearningProgress for %s", session_id)
        return None
