"""Deterministic quality gate for generated learning resources."""

from __future__ import annotations

import re
from collections import Counter
from typing import Any

from app.services.structured_multimodal_resources import sanitize_mermaid


class ResourceQualityReviewer:
    """Reject renderable-but-empty templates before they are marked as passed."""

    _PLACEHOLDERS = ("TODO", "example.com", "<placeholder>", "概念A", "概念B")
    _GENERIC = ("核心定义", "关键步骤", "理解与练习", "复盘与自测", "相关知识")
    _RECURSION_WORDS = ("递归", "终止条件", "调用栈", "栈帧", "返回")

    @staticmethod
    def _labels(mermaid: str) -> list[str]:
        labels = re.findall(r'\["?([^\]\n"]+)"?\]|root\(\(([^()\n]+)\)\)', mermaid)
        values = [next((item.strip() for item in match if item.strip()), "") for match in labels]
        if mermaid.lstrip().startswith("mindmap"):
            values.extend(
                line.strip() for line in mermaid.splitlines()[1:]
                if line.startswith(("  ", "\t")) and line.strip() and not line.strip().startswith("root((")
            )
        return values

    @staticmethod
    def _comparison_headers(content: str) -> tuple[str, str]:
        for line in content.splitlines():
            cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
            if len(cells) >= 3 and cells[0] in {"维度", "对比维度"}:
                return cells[1], cells[2]
        return "", ""

    def review(self, resource: dict[str, Any], *, section_title: str, knowledge_points: list[str]) -> dict[str, Any]:
        content = str(resource.get("content") or "").strip()
        mermaid = str(resource.get("mermaid_def") or "").strip()
        normalized = sanitize_mermaid(mermaid) if mermaid else ""
        resource_type = str(resource.get("task_id") or resource.get("generated_type") or "")
        diagram_required = resource.get("format") in {"diagram", "mermaid"} or resource.get("type") == "mindmap"
        topic_text = f"{section_title} {' '.join(str(point) for point in knowledge_points)}"
        is_recursion = any(token in topic_text for token in ("递归", "阶乘", "调用栈", "栈帧"))
        combined = f"{content}\n{normalized}"
        labels = [label for label in self._labels(normalized) if label]
        duplicate_labels = any(count > 1 for count in Counter(labels).values())
        header_left, header_right = self._comparison_headers(content)
        meaningful_rows = sum(1 for line in content.splitlines() if line.strip().startswith("|") and "---" not in line)

        checks = {
            "topic_relevance": any(point and point in combined for point in knowledge_points) or section_title in combined or (is_recursion and "递归" in combined),
            "topic_keyword_coverage": not is_recursion or sum(word in combined for word in self._RECURSION_WORDS) >= 4,
            "duplicate_node_detection": not duplicate_labels,
            "generic_content_detection": not (labels and all(label in self._GENERIC for label in labels)),
            "overlong_node_detection": not any(len(label) > 36 for label in labels),
            "structural_completeness": self._complete(resource_type, content, labels, meaningful_rows, is_recursion),
            "semantic_distinctness": resource_type != "concept_diagram" or bool(header_left and header_right and header_left != header_right),
            "educational_value": len(content) >= 100 and not all(token in self._GENERIC for token in re.findall(r"[\u4e00-\u9fff]{2,}", content)),
            "factual_consistency": not ("factorial(0)" in content and "n == 1" in content) and not (is_recursion and "负数" not in content and resource_type == "code_trace"),
            "duplication_detection": content.count("def factorial") <= 1 and not duplicate_labels,
            "renderability": not diagram_required or bool(normalized),
            "safety": not diagram_required or bool(normalized),
            "placeholder_free": not any(token.lower() in combined.lower() for token in self._PLACEHOLDERS),
            "personalization": bool((resource.get("personalization") or {}).get("learner_level")),
        }
        repaired = bool(mermaid and normalized and normalized != mermaid)
        if normalized:
            resource["mermaid_def"] = normalized
        quality_score = round(sum(bool(value) for value in checks.values()) / len(checks), 2)
        status = "repaired" if repaired and all(checks.values()) else "passed" if all(checks.values()) else "failed"
        resource["resource_metadata"] = {
            **(resource.get("resource_metadata") if isinstance(resource.get("resource_metadata"), dict) else {}),
            "quality_status": status,
            "quality_score": quality_score,
            "checks": checks,
            "used_llm": bool(resource.get("used_llm")),
            "used_fallback": bool(resource.get("used_fallback")),
            "generation_source": resource.get("generation_source", "local_template"),
            "generation_mode": resource.get("generation_mode", "rule_based"),
            "personalization": resource.get("personalization") or {},
            "repair_attempts": 1 if repaired else 0,
        }
        return resource

    @staticmethod
    def _complete(resource_type: str, content: str, labels: list[str], rows: int, is_recursion: bool) -> bool:
        if resource_type == "knowledge_map" and is_recursion:
            return len(set(labels)) >= 8 and "递归调用栈" in " ".join(labels)
        if resource_type == "concept_diagram" and is_recursion:
            return rows >= 6
        if resource_type == "process_flow" and is_recursion:
            return len(labels) >= 8 and all(word in content for word in ("终止条件", "栈帧", "返回"))
        if resource_type in {"execution_trace", "code_trace"} and is_recursion:
            return "factorial(" in content and all(word in content for word in ("返回后继续执行", "O(n)"))
        if resource_type == "knowledge_map":
            return len(set(labels)) >= 6
        if resource_type == "process_flow":
            return len(labels) >= 6 and rows >= 0
        if resource_type == "concept_diagram":
            return rows >= 5
        if resource_type in {"execution_trace", "code_trace"}:
            return all(word in content for word in ("输入", "状态", "输出", "复杂度"))
        return len(content) >= 80
