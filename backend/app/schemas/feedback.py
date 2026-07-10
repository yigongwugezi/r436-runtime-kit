"""Explicit cross-request feedback signals.

Replaces the implicit ``state.facts["_pending_adjustment"]`` pattern where
GradingAgent results were smuggled into the next request via a hidden dict key.

Now grading feedback flows through a typed :class:`FeedbackSignal` that is:
- Attached to the conversation state explicitly
- Inspected by ConversationAgent at the start of the next request
- Self-describing (no reverse-engineering required to understand the data flow)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class ErrorCategory(str, Enum):
    """Error types produced by GradingAgent — mirrored from grading_agent.py."""
    CONCEPT = "concept"
    CALCULATION = "calculation"
    MISREADING = "misreading"
    METHOD = "method"
    FORGETTING = "forgetting"


ERROR_LABELS: dict[str, str] = {
    "concept":      "概念错误",
    "calculation":  "计算失误",
    "misreading":   "审题偏差",
    "method":       "方法不当",
    "forgetting":   "知识遗忘",
}


@dataclass
class FeedbackSignal:
    """A typed signal carried from one request to the next.

    Unlike the old ``_pending_adjustment`` string, this carries structured
    context so the downstream consumer (ConversationAgent / PlannerAgent)
    can make informed decisions.
    """

    # What triggered this feedback
    source: str = "grading"                     # "grading" | "diagnosis" | "review" | "manual"
    error_type: str = ""                        # one of ErrorCategory values
    error_label: str = ""                       # Chinese label (auto-populated)

    # Context for the next request
    suggested_action: str = ""                  # e.g. "建议重新规划学习路径"
    weak_point_names: list[str] = field(default_factory=list)  # affected knowledge points

    # Timestamp for staleness checks
    created_at: float = 0.0                     # time.time() when created

    def __post_init__(self) -> None:
        if self.error_type and not self.error_label:
            self.error_label = ERROR_LABELS.get(self.error_type, self.error_type)

    @property
    def is_stale(self, max_age_seconds: float = 3600.0) -> bool:
        """Return *True* if this signal is older than *max_age_seconds*."""
        import time
        return (time.time() - self.created_at) > max_age_seconds

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "error_type": self.error_type,
            "error_label": self.error_label,
            "suggested_action": self.suggested_action,
            "weak_point_names": self.weak_point_names,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "FeedbackSignal":
        return cls(
            source=str(d.get("source", "grading")),
            error_type=str(d.get("error_type", "")),
            error_label=str(d.get("error_label", "")),
            suggested_action=str(d.get("suggested_action", "")),
            weak_point_names=list(d.get("weak_point_names", [])),
            created_at=float(d.get("created_at", 0.0)),
        )

    @classmethod
    def from_grading_result(cls, grading_result: dict[str, Any]) -> "FeedbackSignal":
        """Create a signal from a GradingAgent result dict."""
        import time
        et = str(grading_result.get("error_type", "")).strip()
        return cls(
            source="grading",
            error_type=et,
            suggested_action="建议重新规划学习路径，重点强化该知识点",
            created_at=time.time(),
        )
