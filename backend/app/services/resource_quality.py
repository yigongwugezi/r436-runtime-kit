"""Small deterministic quality gate for locally generated P4 resources."""

from __future__ import annotations

from typing import Any

from app.services.structured_multimodal_resources import sanitize_mermaid


class ResourceQualityReviewer:
    """Validate one resource once; callers fall back instead of retrying forever."""

    _PLACEHOLDERS = ("TODO", "example.com", "<placeholder>", "概念A", "概念B")

    def review(self, resource: dict[str, Any], *, section_title: str, knowledge_points: list[str]) -> dict[str, Any]:
        content = str(resource.get("content") or "").strip()
        mermaid = str(resource.get("mermaid_def") or "").strip()
        normalized = sanitize_mermaid(mermaid) if mermaid else ""
        diagram_required = resource.get("format") in {"diagram", "mermaid"} or resource.get("type") == "mindmap"
        checks = {
            "topic_relevance": section_title in content or section_title in normalized or any(point in content or point in normalized for point in knowledge_points),
            "factual_consistency": not any(key in content for key in ("major_background", "knowledge_base", "learning_goal")),
            "structural_completeness": len(content) >= 60,
            "renderability": not diagram_required or bool(normalized),
            "placeholder_free": not any(token.lower() in content.lower() for token in self._PLACEHOLDERS),
            "personalization": bool((resource.get("personalization") or {}).get("learner_level")),
            "safety": not diagram_required or bool(normalized),
        }
        repaired = bool(mermaid and normalized and normalized != mermaid)
        if normalized:
            resource["mermaid_def"] = normalized
        quality_score = round(sum(bool(value) for value in checks.values()) / len(checks), 2)
        status = "repaired" if repaired and quality_score == 1 else "passed" if quality_score == 1 else "failed"
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
