"""Knowledge point mapping resolution and per-KP result computation.

Provides the bridge between the legacy string-list ``knowledge_points``
JSON field on questions and the formal ``QuestionKnowledgePointMappingModel``
table.  During grading, every answer record is decomposed into per-knowledge-
point results weighted by the mapping weights.
"""

from __future__ import annotations

from dataclasses import dataclass
import logging

from sqlalchemy.orm import Session

from app.db.models import (
    AnswerRecordModel,
    PracticeQuestionModel,
    QuestionKnowledgePointMappingModel,
)
from app.db.repository import ensure_question_kp_mappings as _repo_ensure_mappings

logger = logging.getLogger(__name__)

# ── Sentinel for unmapped questions ──────────────────────────────────────

UNMAPPED_KEY = "unmapped"

# ── Grading confidence by question type ───────────────────────────────────
# These reflect how reliably rule-based grading can determine correctness.
_GRADING_CONFIDENCE: dict[str, float] = {
    "choice": 0.95,
    "truefalse": 0.90,
    "fill": 0.80,
    "shortanswer": 0.75,
}

# ── KnowledgePointResult ──────────────────────────────────────────────────


@dataclass
class KnowledgePointResult:
    """Computed per-knowledge-point result for a single graded answer.

    When a question maps to N knowledge points, N instances of this
    class are produced — one per mapping — with scores weighted
    proportionally.
    """

    knowledge_point_key: str
    knowledge_point_label: str
    question_id: str
    attempt_id: str
    raw_score: float
    max_score: float
    normalized_score: float
    weight: float
    weighted_score: float
    mapping_confidence: float
    grading_confidence: float
    is_correct: bool
    error_type: str | None
    assessment_eligible: bool
    evidence_id: str | None = None

    def to_dict(self) -> dict:
        return {
            "knowledgePointKey": self.knowledge_point_key,
            "knowledgePointLabel": self.knowledge_point_label,
            "questionId": self.question_id,
            "attemptId": self.attempt_id,
            "rawScore": self.raw_score,
            "maxScore": self.max_score,
            "normalizedScore": self.normalized_score,
            "weight": self.weight,
            "weightedScore": self.weighted_score,
            "mappingConfidence": self.mapping_confidence,
            "gradingConfidence": self.grading_confidence,
            "isCorrect": self.is_correct,
            "errorType": self.error_type,
            "assessmentEligible": self.assessment_eligible,
        }


# ── Mapping resolution ────────────────────────────────────────────────────


def resolve_mappings(
    db: Session,
    question: PracticeQuestionModel,
    subject_id: str | None = None,
) -> list[QuestionKnowledgePointMappingModel]:
    """Resolve KP mappings for a question, creating fallbacks from legacy data.

    Returns the list of mappings, or an empty list for unmapped questions.
    """
    return _repo_ensure_mappings(db, question, subject_id=subject_id)


# ── Per-KP result computation ─────────────────────────────────────────────


def compute_results(
    question: PracticeQuestionModel,
    mappings: list[QuestionKnowledgePointMappingModel],
    answer_record: AnswerRecordModel,
    attempt_id: str,
    assessment_eligible: bool,
) -> list[KnowledgePointResult]:
    """Compute per-KP results from a single graded answer record.

    Each mapping produces one ``KnowledgePointResult``.  The question's
    raw score is distributed across KPs according to mapping weights.
    """
    if not mappings:
        # Unmapped question — produce a single sentinel result.
        # These are still scorable but excluded from precise diagnosis.
        q_score = float(answer_record.total_score or 0)
        q_max = 100.0
        return [
            KnowledgePointResult(
                knowledge_point_key=UNMAPPED_KEY,
                knowledge_point_label="(unmapped)",
                question_id=question.question_id,
                attempt_id=attempt_id,
                raw_score=q_score,
                max_score=q_max,
                normalized_score=q_score / max(q_max, 1.0),
                weight=1.0,
                weighted_score=q_score,
                mapping_confidence=0.0,
                grading_confidence=_grading_confidence(question.type),
                is_correct=q_score >= q_max,
                error_type=answer_record.error_type,
                assessment_eligible=assessment_eligible,
            )
        ]

    q_score = float(answer_record.total_score or 0)
    q_max = 100.0
    normalized = q_score / max(q_max, 1.0)
    is_correct = q_score >= q_max
    grading_conf = _grading_confidence(question.type)

    results: list[KnowledgePointResult] = []
    for m in mappings:
        weighted = q_score * m.weight
        results.append(
            KnowledgePointResult(
                knowledge_point_key=m.knowledge_point_key,
                knowledge_point_label=m.knowledge_point_label or m.knowledge_point_key,
                question_id=question.question_id,
                attempt_id=attempt_id,
                raw_score=q_score,
                max_score=q_max,
                normalized_score=normalized,
                weight=m.weight,
                weighted_score=weighted,
                mapping_confidence=m.confidence,
                grading_confidence=grading_conf,
                is_correct=is_correct,
                error_type=answer_record.error_type,
                assessment_eligible=assessment_eligible,
            )
        )
    return results


def compute_all_results(
    db: Session,
    linked_questions: list[PracticeQuestionModel],
    answer_records: dict[str, AnswerRecordModel],
    attempt_id: str,
    subject_id: str | None,
    assessment_eligible: bool,
) -> list[dict]:
    """Compute KPRs for every question in a submission.

    Args:
        db: Active DB session.
        linked_questions: Questions that were answered.
        answer_records: question_id → AnswerRecordModel mapping.
        attempt_id: The attempt these results belong to.
        subject_id: Subject context for mapping resolution.
        assessment_eligible: Whether this attempt counts toward mastery.

    Returns:
        List of dicts ready for JSON serialisation.
    """
    all_results: list[dict] = []
    for pq in linked_questions:
        ar = answer_records.get(pq.question_id)
        if ar is None:
            continue
        mappings = resolve_mappings(db, pq, subject_id=subject_id)
        kprs = compute_results(pq, mappings, ar, attempt_id, assessment_eligible)
        all_results.extend(r.to_dict() for r in kprs)
    return all_results


# ── Helpers ───────────────────────────────────────────────────────────────


def _grading_confidence(question_type: str) -> float:
    """Return the grading confidence for a question type.

    Rule-based grading for choice/truefalse is highly reliable;
    short-answer grading relies on LLM judgment and is less so.
    """
    qtype = (question_type or "choice").lower()
    return _GRADING_CONFIDENCE.get(qtype, 0.80)


def get_highest_weight_label(
    mappings: list[QuestionKnowledgePointMappingModel],
    fallback: str = "",
) -> str:
    """Return the label of the highest-weight mapping, for backward compat.

    This replaces the old ``knowledge_points[0]`` pattern used to populate
    the per-question-response ``knowledgePoint`` field.
    """
    if not mappings:
        return fallback
    return mappings[0].knowledge_point_label or mappings[0].knowledge_point_key
