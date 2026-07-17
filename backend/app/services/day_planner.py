"""
DayPlanner — 将 stages→chapters→sections 按天组织为可执行的学习计划。

核心思路：
- 天是计划的第一级组织单位，不再是章节
- 每天的内容可以混合：新课(new)、复习(review)、练习(practice)、诊断(diagnosis)
- 动态调整时只重算未来 N 天，不影响已完成的计划
"""

from __future__ import annotations

import logging
import time
import re
from typing import Any

logger = logging.getLogger(__name__)

# ── 常量 ──────────────────────────────────────────────────────────────────

DEFAULT_DAILY_MINUTES = 60
DIAGNOSIS_INTERVAL_DAYS = 5  # 每 N 天插入一个诊断日

# ── 数据结构 ──────────────────────────────────────────────────────────────


def make_day_item_id(day: int, index: int) -> str:
    return f"day{day}_item{index}"


# ── 核心：从 stages 生成 day_plan ────────────────────────────────────────


def flatten_sections(stages: list[dict]) -> list[dict]:
    """将 stages→chapters→sections 拍平为便于处理的 section 列表。"""
    sections = []
    for stage in stages:
        stage_title = str(stage.get("title", ""))
        for ch in stage.get("chapters", []):
            for sec in ch.get("sections", []):
                sections.append({
                    "section_id": sec.get("section_id", ""),
                    "title": sec.get("title", ""),
                    "estimated_minutes": sec.get("estimated_minutes", 45),
                    "content_type": sec.get("content_type", "lecture"),
                    "knowledge_points": sec.get("knowledge_points", []),
                    "stage_title": stage_title,
                    "adjustment": sec.get("_adjustment", ""),
                    "adjustment_reason": sec.get("_adjustment_reason", ""),
                    "weak_kps": sec.get("_weak_kps", []),
                })
    return sections


def classify_section(sec: dict, mastery_map: dict[str, dict]) -> list[dict]:
    """将单个 section 分类为 1~N 个 DayPlanItem。

    根据掌握度决定行为：
    - 全部精通 (accelerated) → 快速回顾 (review)
    - 全部薄弱 (strengthened) → 新课 + 练习 (new + practice)
    - 混合 (mixed) → 新课 + 薄弱点练习
    - 正常 / 无数据 → 新课 (new)
    """
    items = []
    adj = sec.get("adjustment", "")
    base_minutes = sec.get("estimated_minutes", 45)
    sec_id = sec.get("section_id", "")
    title = sec.get("title", "")
    stage = sec.get("stage_title", "")

    if adj == "accelerated":
        # 已掌握 → 快速回顾
        items.append({
            "type": "review",
            "title": f"快速回顾：{title}",
            "minutes": max(10, base_minutes // 4),
            "source_section_id": sec_id,
            "source_stage": stage,
            "description": sec.get("adjustment_reason", "已掌握内容，快速过一遍保持记忆"),
            "adjustment": "accelerated",
            "weak_kps": [],
        })
    elif adj == "strengthened":
        # 薄弱 → 新课 + 练习
        items.append({
            "type": "new",
            "title": title,
            "minutes": int(base_minutes * 0.6),
            "source_section_id": sec_id,
            "source_stage": stage,
            "description": sec.get("adjustment_reason", "需重点学习"),
            "adjustment": "strengthened",
            "weak_kps": sec.get("weak_kps", []),
        })
        practice_minutes = max(15, int(base_minutes * 0.4))
        items.append({
            "type": "practice",
            "title": f"巩固练习：{title}",
            "minutes": practice_minutes,
            "source_section_id": sec_id,
            "source_stage": stage,
            "description": "薄弱点专项练习，巩固理解",
            "adjustment": "strengthened",
            "weak_kps": sec.get("weak_kps", []),
        })
    elif adj == "mixed":
        # 混合 → 精简新课 + 薄弱点练习
        items.append({
            "type": "new",
            "title": title,
            "minutes": int(base_minutes * 0.5),
            "source_section_id": sec_id,
            "source_stage": stage,
            "description": sec.get("adjustment_reason", ""),
            "adjustment": "mixed",
            "weak_kps": sec.get("weak_kps", []),
        })
        items.append({
            "type": "practice",
            "title": f"重点突破：{'、'.join(sec.get('weak_kps', []))}",
            "minutes": max(15, int(base_minutes * 0.3)),
            "source_section_id": sec_id,
            "source_stage": stage,
            "description": f"集中训练薄弱知识点",
            "adjustment": "mixed",
            "weak_kps": sec.get("weak_kps", []),
        })
    else:
        # 正常 / 无调整 → 新课
        items.append({
            "type": "new",
            "title": title,
            "minutes": base_minutes,
            "source_section_id": sec_id,
            "source_stage": stage,
            "description": sec.get("goal", "") or f"学习{title}的核心内容",
            "adjustment": None,
            "weak_kps": [],
        })

    return items


def build_day_plan(
    stages: list[dict],
    mastery_map: dict[str, dict] | None = None,
    daily_minutes: int = DEFAULT_DAILY_MINUTES,
) -> dict:
    """从 stages 生成按天组织的学习计划。

    Args:
        stages: planner 产出的 stages→chapters→sections 结构
        mastery_map: {kp_name: {score, level}}，来自诊断
        daily_minutes: 每天可用学习分钟数

    Returns:
        day_plan dict: {days: [{day, total_minutes, items}], version, generated_at}
    """
    if not stages:
        return {"days": [], "version": 0, "generated_at": time.time()}

    mastery_map = mastery_map or {}
    sections = flatten_sections(stages)

    # 每个 section → 1~N 个 item
    all_items: list[dict] = []
    for sec in sections:
        all_items.extend(classify_section(sec, mastery_map))

    # 分配到天
    days: list[dict] = []
    current_day_items: list[dict] = []
    current_minutes = 0
    day_count = 1

    for item in all_items:
        mins = item["minutes"]
        if current_minutes + mins > daily_minutes and current_day_items:
            days.append({
                "day": day_count,
                "total_minutes": current_minutes,
                "items": [dict(item, id=make_day_item_id(day_count, idx))
                         for idx, item in enumerate(current_day_items)],
            })
            day_count += 1
            current_day_items = []
            current_minutes = 0

        # 定期插入诊断日
        if day_count % DIAGNOSIS_INTERVAL_DAYS == 0 and not current_day_items:
            days.append({
                "day": day_count,
                "total_minutes": 20,
                "items": [{
                    "id": make_day_item_id(day_count, 0),
                    "type": "diagnosis",
                    "title": f"第{day_count}天诊断：阶段掌握度测验",
                    "minutes": 20,
                    "source_section_id": "",
                    "source_stage": "",
                    "description": "检测近期学习效果，发现薄弱点以动态调整后续计划",
                    "adjustment": None,
                    "weak_kps": [],
                }],
            })
            day_count += 1

        current_day_items.append(item)
        current_minutes += mins

    # 最后几天
    if current_day_items:
        days.append({
            "day": day_count,
            "total_minutes": current_minutes,
            "items": [dict(item, id=make_day_item_id(day_count, idx))
                     for idx, item in enumerate(current_day_items)],
        })

    return {
        "days": days,
        "version": int(time.time() * 1000),
        "generated_at": time.time(),
    }


# ── 动态调整：基于新诊断修改已有 day_plan ────────────────────────────────


# ── 差异计算 ────────────────────────────────────────────────────────────────


def compute_diff(old_stages: list[dict], new_stages: list[dict]) -> dict:
    """计算两个路径版本的差异，用于 revision review。

    按 section_id 逐个匹配，输出结构化变化列表。
    """
    # 构建旧路径的 section lookup
    old_map: dict[str, dict] = {}
    for s in old_stages:
        for ch in s.get("chapters", []):
            for sec in ch.get("sections", []):
                sid = sec.get("section_id", "")
                if sid:
                    old_map[sid] = {**sec, "_stage_title": s.get("title", "")}

    changed: list[dict] = []
    matched_new: set[str] = set()
    for s in new_stages:
        for ch in s.get("chapters", []):
            for sec in ch.get("sections", []):
                sid = sec.get("section_id", "")
                if not sid:
                    continue
                matched_new.add(sid)
                old_sec = old_map.get(sid)
                if old_sec:
                    old_mins = old_sec.get("estimated_minutes", 45)
                    new_mins = sec.get("estimated_minutes", 45)
                    old_ct = old_sec.get("content_type", "lecture")
                    new_ct = sec.get("content_type", "lecture")
                    if old_mins != new_mins or old_ct != new_ct:
                        changed.append({
                            "section_id": sid,
                            "title": sec.get("title", ""),
                            "stage_title": s.get("title", ""),
                            "old_minutes": old_mins,
                            "new_minutes": new_mins,
                            "old_content_type": old_ct,
                            "new_content_type": new_ct,
                            "adjustment": sec.get("_adjustment", ""),
                            "reason": sec.get("_adjustment_reason", ""),
                        })
                else:
                    # 新出现的 section
                    changed.append({
                        "section_id": sid,
                        "title": sec.get("title", ""),
                        "stage_title": s.get("title", ""),
                        "old_minutes": 0,
                        "new_minutes": sec.get("estimated_minutes", 45),
                        "old_content_type": "",
                        "new_content_type": sec.get("content_type", "lecture"),
                        "adjustment": "added",
                        "reason": "新增小节",
                    })

    # 旧路径中已移除的 section
    for sid, old_sec in old_map.items():
        if sid not in matched_new:
            changed.append({
                "section_id": sid,
                "title": old_sec.get("title", ""),
                "stage_title": old_sec.get("_stage_title", ""),
                "old_minutes": old_sec.get("estimated_minutes", 45),
                "new_minutes": 0,
                "old_content_type": old_sec.get("content_type", "lecture"),
                "new_content_type": "",
                "adjustment": "removed",
                "reason": "已移除",
            })

    old_total = sum(
        sec.get("estimated_minutes", 45)
        for s in old_stages for ch in s.get("chapters", []) for sec in ch.get("sections", [])
    )
    new_total = sum(
        sec.get("estimated_minutes", 45)
        for s in new_stages for ch in s.get("chapters", []) for sec in ch.get("sections", [])
    )

    return {
        "changed_sections": changed,
        "unchanged_count": sum(
            1 for sid in old_map if sid in matched_new
            and sid not in {c["section_id"] for c in changed}
        ),
        "total_minutes_before": old_total,
        "total_minutes_after": new_total,
        "days_impact": "increase" if new_total > old_total else "decrease" if new_total < old_total else "no_change",
        "summary": f"{len(changed)} 个小节变化，总时长 {old_total}→{new_total} 分钟",
    }


def adjust_day_plan(
    existing_plan: dict,
    stages: list[dict],
    mastery_map: dict[str, dict],
    daily_minutes: int = DEFAULT_DAILY_MINUTES,
    lookahead_days: int = 7,
) -> dict:
    """基于新诊断结果，增量调整 day_plan 中未来 N 天的内容。

    策略：
    - 已完成的天（status=completed）不动
    - 未来 N 天重新分配
    - 调整标记会更新
    """
    days = existing_plan.get("days", [])

    # 找到第一个未完成的天
    cutoff = 0
    for i, d in enumerate(days):
        items = d.get("items", [])
        all_done = all(item.get("status") == "completed" for item in items)
        if not all_done:
            cutoff = i
            break
    else:
        cutoff = len(days)  # 全部完成，追加新计划

    # 保留已完成的天
    preserved = days[:cutoff]
    completed_days = len(preserved)

    # 未来 N 天重新规划
    future_items: list[dict] = []
    sections = flatten_sections(stages)

    # 只取调整后有变化的 section
    for sec in sections:
        adj = sec.get("adjustment", "")
        if adj in ("strengthened", "mixed", "accelerated"):
            future_items.extend(classify_section(sec, mastery_map))

    if not future_items:
        # 无变化，保持原样
        return existing_plan

    # 重新分配到天
    new_days: list[dict] = []
    current_items: list[dict] = []
    current_mins = 0
    day_idx = completed_days + 1

    for item in future_items[:lookahead_days * 2]:
        mins = item["minutes"]
        if current_mins + mins > daily_minutes and current_items:
            new_days.append({
                "day": day_idx,
                "total_minutes": current_mins,
                "items": [dict(it, id=make_day_item_id(day_idx, idx))
                         for idx, it in enumerate(current_items)],
            })
            day_idx += 1
            current_items = []
            current_mins = 0
        current_items.append(item)
        current_mins += mins

    if current_items:
        new_days.append({
            "day": day_idx,
            "total_minutes": current_mins,
            "items": [dict(it, id=make_day_item_id(day_idx, idx))
                     for idx, it in enumerate(current_items)],
        })

    return {
        "days": preserved + new_days,
        "version": int(time.time() * 1000),
        "generated_at": time.time(),
        "_adjusted_days": [d["day"] for d in new_days],
    }
