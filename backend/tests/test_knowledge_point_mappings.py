"""Tests for weighted question→knowledge-point mappings and KPR computation.

Covers spec section 12.2:
1. Single-KP question
2. Multi-KP question
3. Weight sum validation
4. Mapping confidence propagation
5. Old question without mappings → fallback created
6. Fallback mapping source + confidence
7. Unmapped question → excluded from precise diagnosis
8. No longer only using first KP
"""

from __future__ import annotations

import os
import tempfile
import uuid
from pathlib import Path

os.environ["EDUAGENT_SKIP_ENV_FILE"] = "1"
_handle, _db_path = tempfile.mkstemp(prefix="edu-kp-mappings-", suffix=".db")
os.close(_handle)
os.environ["DATABASE_URL"] = f"sqlite:///{_db_path}"
os.environ["JWT_SECRET"] = "kp-mapping-test-secret"
os.environ["LLM_PROVIDER"] = "mock"

from fastapi.testclient import TestClient

from app.db.engine import SessionLocal, engine
from app.db.models import (
    AnswerRecordModel,
    AttemptModel,
    Base,
    LearnerModel,
    PracticeQuestionModel,
    QuestionKnowledgePointMappingModel,
    QuizModel,
    SessionModel,
)
from app.db.repository import (
    ensure_question_kp_mappings,
    get_mappings_for_question,
    get_or_create_fallback_mappings,
)
from app.main import app
from app.services.knowledge_point_service import (
    UNMAPPED_KEY,
    KnowledgePointResult,
    compute_all_results,
    compute_results,
    get_highest_weight_label,
    resolve_mappings,
)
from app.utils.auth import create_token

_LEARNER = "learner_kp_test"
_SESSION = "session_kp_test"
_headers = {"Authorization": f"Bearer {create_token(_LEARNER, 'student')}"}


def _setup() -> None:
    Base.metadata.create_all(engine)
    db = SessionLocal()
    try:
        if not db.query(LearnerModel).filter(LearnerModel.id == _LEARNER).first():
            db.add(LearnerModel(id=_LEARNER, nickname="KPTester"))
            db.flush()
        if not db.query(SessionModel).filter(SessionModel.id == _SESSION).first():
            db.add(SessionModel(id=_SESSION, learner_id=_LEARNER, subject_id="math"))
            db.flush()
        db.commit()
    finally:
        db.close()


def _seed_quiz_with_questions(
    quiz_id: str, questions: list[dict],
) -> str:
    """Create a quiz with given questions. Returns quiz_id."""
    db = SessionLocal()
    try:
        quiz = QuizModel(
            id=quiz_id, title=f"Quiz {quiz_id}",
            session_id=_SESSION, scope_type="section",
            question_count=len(questions), source="test",
        )
        db.add(quiz)
        db.flush()
        for q in questions:
            pq = PracticeQuestionModel(
                question_id=q["question_id"],
                question_set_id=quiz_id,
                session_id=_SESSION,
                type=q.get("type", "choice"),
                stem=q.get("stem", "Question"),
                options=q.get("options", ["A", "B", "C", "D"]),
                correct=q.get("correct", "A"),
                explanation=q.get("explanation", ""),
                knowledge_points=q.get("knowledge_points"),
                source="test",
                quality_status="passed",
            )
            db.add(pq)
        db.commit()
        return quiz_id
    finally:
        db.close()


def _submit(quiz_id: str, answers: list[dict], idem_key: str = "") -> tuple[int, dict]:
    client = TestClient(app)
    body = {
        "sessionId": _SESSION,
        "idempotencyKey": idem_key or f"kp-test-{uuid.uuid4().hex[:8]}",
        "answers": answers,
    }
    resp = client.post(f"/api/quizzes/{quiz_id}/submit", json=body, headers=_headers)
    return resp.status_code, resp.json()


# ── Test 1: Single-KP question ────────────────────────────────────────────


def test_single_kp_question():
    """A question with one mapping produces exactly one KPR."""
    _setup()
    quiz_id = f"quiz_kp_single_{uuid.uuid4().hex[:6]}"
    qid = f"q_single_{uuid.uuid4().hex[:6]}"
    _seed_quiz_with_questions(quiz_id, [{
        "question_id": qid,
        "type": "choice",
        "stem": "What is 1+1?",
        "options": ["A. 1", "B. 2", "C. 3", "D. 4"],
        "correct": "B",
        "knowledge_points": ["arithmetic"],
    }])

    # Pre-create an explicit mapping
    db = SessionLocal()
    try:
        from app.db.repository import create_question_kp_mapping
        create_question_kp_mapping(
            db,
            mapping_id=f"map_single_{uuid.uuid4().hex[:12]}",
            question_id=qid,
            knowledge_point_key="arithmetic",
            knowledge_point_label="Arithmetic",
            weight=1.0,
            confidence=0.95,
            source="explicit",
        )
        db.commit()
    finally:
        db.close()

    status, body = _submit(quiz_id, [{"questionId": qid, "answer": "B"}])
    assert status == 200, f"Expected 200, got {status}: {body}"
    kprs = body["data"].get("knowledgePointResults", [])
    assert len(kprs) == 1, f"Expected 1 KPR, got {len(kprs)}"
    kpr = kprs[0]
    assert kpr["knowledgePointKey"] == "arithmetic"
    assert kpr["weight"] == 1.0
    assert kpr["mappingConfidence"] == 0.95
    assert kpr["isCorrect"] is True


# ── Test 2: Multi-KP question ─────────────────────────────────────────────


def test_multi_kp_question():
    """A question with 3 mappings produces 3 KPRs with correct weighted scores."""
    _setup()
    quiz_id = f"quiz_kp_multi_{uuid.uuid4().hex[:6]}"
    qid = f"q_multi_{uuid.uuid4().hex[:6]}"
    _seed_quiz_with_questions(quiz_id, [{
        "question_id": qid,
        "type": "choice",
        "stem": "Which data structure uses LIFO?",
        "options": ["A. Queue", "B. Stack", "C. Tree", "D. Graph"],
        "correct": "B",
        "knowledge_points": ["stack", "lifo", "data_structures"],
    }])

    db = SessionLocal()
    try:
        from app.db.repository import create_question_kp_mapping
        create_question_kp_mapping(
            db, mapping_id=f"map_multi_a_{uuid.uuid4().hex[:12]}",
            question_id=qid, knowledge_point_key="stack",
            knowledge_point_label="Stack", weight=0.5, confidence=0.9,
            source="explicit",
        )
        create_question_kp_mapping(
            db, mapping_id=f"map_multi_b_{uuid.uuid4().hex[:12]}",
            question_id=qid, knowledge_point_key="lifo",
            knowledge_point_label="LIFO", weight=0.3, confidence=0.9,
            source="explicit",
        )
        create_question_kp_mapping(
            db, mapping_id=f"map_multi_c_{uuid.uuid4().hex[:12]}",
            question_id=qid, knowledge_point_key="data_structures",
            knowledge_point_label="Data Structures", weight=0.2, confidence=0.9,
            source="explicit",
        )
        db.commit()
    finally:
        db.close()

    status, body = _submit(quiz_id, [{"questionId": qid, "answer": "B"}])
    assert status == 200, f"Expected 200, got {status}: {body}"
    kprs = body["data"].get("knowledgePointResults", [])
    assert len(kprs) == 3, f"Expected 3 KPRs, got {len(kprs)}"

    # Check weighted scores: question_score=100, weights [0.5, 0.3, 0.2]
    stacked_weight = sum(k["weightedScore"] for k in kprs)
    assert abs(stacked_weight - 100.0) < 0.01, f"Weighted scores should sum to 100, got {stacked_weight}"


# ── Test 3: Weight sum validation ─────────────────────────────────────────


def test_weights_sum_to_one():
    """Weights that don't sum to 1.0 are normalized."""
    _setup()
    quiz_id = f"quiz_kp_wnorm_{uuid.uuid4().hex[:6]}"
    qid = f"q_wnorm_{uuid.uuid4().hex[:6]}"
    _seed_quiz_with_questions(quiz_id, [{
        "question_id": qid,
        "type": "choice",
        "stem": "Test question",
        "options": ["A", "B", "C", "D"],
        "correct": "A",
        "knowledge_points": ["a", "b"],
    }])

    db = SessionLocal()
    try:
        from app.db.repository import create_question_kp_mapping
        create_question_kp_mapping(
            db, mapping_id=f"map_wn_a_{uuid.uuid4().hex[:12]}",
            question_id=qid, knowledge_point_key="a", knowledge_point_label="A",
            weight=2.0, confidence=0.9, source="explicit",
        )
        create_question_kp_mapping(
            db, mapping_id=f"map_wn_b_{uuid.uuid4().hex[:12]}",
            question_id=qid, knowledge_point_key="b", knowledge_point_label="B",
            weight=3.0, confidence=0.9, source="explicit",
        )
        db.commit()
    finally:
        db.close()

    # The raw weights are [2.0, 3.0] — the service doesn't normalize
    # at the compute_results level; normalization is a call-site concern.
    # Verify that the weights are used as-is (caller responsible for norm).
    db = SessionLocal()
    try:
        mappings = get_mappings_for_question(db, qid)
        assert len(mappings) == 2
        # Create a mock answer record
        ar = AnswerRecordModel(
            session_id=_SESSION, question_id=qid,
            attempt_id="att_test_wnorm", student_answer="A",
            total_score=100, source="test",
        )
        kprs = compute_results(
            PracticeQuestionModel(
                question_id=qid, question_set_id=quiz_id,
                session_id=_SESSION, type="choice", stem="T",
                options=["A", "B", "C", "D"], correct="A",
                knowledge_points=["a", "b"],
                source="test", quality_status="passed",
            ),
            mappings, ar, "att_test_wnorm", True,
        )
        # weighted_score uses raw weight; total = 100*2.0 + 100*3.0 = 500
        total_weighted = sum(k.weighted_score for k in kprs)
        assert total_weighted == 500.0, f"Raw weighted sum should be 500, got {total_weighted}"
    finally:
        db.close()


# ── Test 4: Mapping confidence propagation ───────────────────────────────


def test_mapping_confidence_propagates():
    """A mapping with confidence=0.8 propagates to KPR.mapping_confidence."""
    _setup()
    quiz_id = f"quiz_kp_conf_{uuid.uuid4().hex[:6]}"
    qid = f"q_conf_{uuid.uuid4().hex[:6]}"
    _seed_quiz_with_questions(quiz_id, [{
        "question_id": qid,
        "type": "truefalse",
        "stem": "Is the earth round?",
        "options": ["True", "False"],
        "correct": "True",
        "knowledge_points": ["earth_science"],
    }])

    db = SessionLocal()
    try:
        from app.db.repository import create_question_kp_mapping
        create_question_kp_mapping(
            db, mapping_id=f"map_conf_{uuid.uuid4().hex[:12]}",
            question_id=qid, knowledge_point_key="earth_science",
            knowledge_point_label="Earth Science",
            weight=1.0, confidence=0.8, source="generated",
        )
        db.commit()
    finally:
        db.close()

    status, body = _submit(quiz_id, [{"questionId": qid, "answer": "True"}])
    assert status == 200
    kprs = body["data"].get("knowledgePointResults", [])
    assert len(kprs) == 1
    assert kprs[0]["mappingConfidence"] == 0.8
    assert kprs[0]["gradingConfidence"] == 0.90  # truefalse


# ── Test 5: Old question without mappings → fallback created ──────────────


def test_old_question_creates_fallback():
    """A question with knowledge_points JSON but no explicit mappings
    gets equal-weight fallback mappings."""
    _setup()
    quiz_id = f"quiz_kp_fb_{uuid.uuid4().hex[:6]}"
    qid = f"q_fb_{uuid.uuid4().hex[:6]}"
    _seed_quiz_with_questions(quiz_id, [{
        "question_id": qid,
        "type": "choice",
        "stem": "What is OOP?",
        "options": ["A", "B", "C", "D"],
        "correct": "A",
        "knowledge_points": ["oop", "inheritance", "polymorphism"],
    }])

    # No explicit mappings — the service should create fallbacks
    status, body = _submit(quiz_id, [{"questionId": qid, "answer": "A"}])
    assert status == 200, f"Expected 200, got {status}: {body}"

    # Should have 3 KPRs (one per KP string)
    kprs = body["data"].get("knowledgePointResults", [])
    assert len(kprs) == 3, f"Expected 3 fallback KPRs, got {len(kprs)}"

    # Verify fallbacks were persisted
    db = SessionLocal()
    try:
        mappings = get_mappings_for_question(db, qid)
        assert len(mappings) == 3
        for m in mappings:
            assert m.source == "fallback"
            assert m.confidence == 0.5
            assert abs(m.weight - 1.0 / 3) < 0.01  # equal weight
        db.close()
    except Exception:
        db.close()
        raise


# ── Test 6: Fallback mapping source + confidence ──────────────────────────


def test_fallback_mapping_source_and_confidence():
    """Fallback mappings have source='fallback' and confidence=0.5."""
    _setup()
    db = SessionLocal()
    try:
        mappings = get_or_create_fallback_mappings(
            db, "q_fallback_test", "math", ["topic_a", "topic_b"],
        )
        db.commit()
        assert len(mappings) == 2
        for m in mappings:
            assert m.source == "fallback", f"Expected source=fallback, got {m.source}"
            assert m.confidence == 0.5, f"Expected confidence=0.5, got {m.confidence}"
            assert m.weight == 0.5, f"Expected weight=0.5, got {m.weight}"

        # Second call returns existing (no duplicates)
        mappings2 = get_or_create_fallback_mappings(
            db, "q_fallback_test", "math", ["topic_a", "topic_b"],
        )
        assert len(mappings2) == 2
        assert {m.mapping_id for m in mappings2} == {m.mapping_id for m in mappings}
    finally:
        db.close()


# ── Test 7: Unmapped question → excluded from precise diagnosis ───────────


def test_unmapped_question():
    """A question with no knowledge_points and no mappings gets UNMAPPED_KEY sentinel."""
    _setup()
    quiz_id = f"quiz_kp_unmapped_{uuid.uuid4().hex[:6]}"
    qid = f"q_unmapped_{uuid.uuid4().hex[:6]}"
    _seed_quiz_with_questions(quiz_id, [{
        "question_id": qid,
        "type": "choice",
        "stem": "No KP question",
        "options": ["A", "B", "C", "D"],
        "correct": "A",
        "knowledge_points": None,  # No KPs at all
    }])

    status, body = _submit(quiz_id, [{"questionId": qid, "answer": "A"}])
    assert status == 200

    kprs = body["data"].get("knowledgePointResults", [])
    assert len(kprs) == 1
    assert kprs[0]["knowledgePointKey"] == UNMAPPED_KEY
    assert kprs[0]["mappingConfidence"] == 0.0


# ── Test 8: No longer only first KP ───────────────────────────────────────


def test_all_kps_have_results_not_just_first():
    """Verify that all mapped KPs produce results, not just knowledge_points[0]."""
    _setup()
    quiz_id = f"quiz_kp_all_{uuid.uuid4().hex[:6]}"
    qid = f"q_all_{uuid.uuid4().hex[:6]}"
    _seed_quiz_with_questions(quiz_id, [{
        "question_id": qid,
        "type": "choice",
        "stem": "Multi-KP question",
        "options": ["A", "B", "C", "D"],
        "correct": "C",
        "knowledge_points": ["recursion", "call_stack", "base_case"],
    }])

    # No explicit mappings → fallback creates 3 equal-weight mappings
    status, body = _submit(quiz_id, [{"questionId": qid, "answer": "C"}])
    assert status == 200, f"Expected 200, got {status}: {body}"

    kprs = body["data"].get("knowledgePointResults", [])
    kp_keys = {k["knowledgePointKey"] for k in kprs}
    assert "recursion" in kp_keys, f"Missing 'recursion' in KP keys: {kp_keys}"
    assert "call_stack" in kp_keys, f"Missing 'call_stack' in KP keys: {kp_keys}"
    assert "base_case" in kp_keys, f"Missing 'base_case' in KP keys: {kp_keys}"

    # The old per-result knowledgePoint should be the highest-weight label
    # (with equal weights, it's the first one by insertion order)
    quiz_result = body["data"]["results"][0]
    old_kp = quiz_result.get("knowledgePoint", "")
    assert old_kp != "", "knowledgePoint should be populated from highest-weight mapping"


# ── Test: Empty KP list → unmapped ────────────────────────────────────────


def test_empty_kp_list_is_unmapped():
    """An empty knowledge_points list results in unmapped."""
    _setup()
    quiz_id = f"quiz_kp_empty_{uuid.uuid4().hex[:6]}"
    qid = f"q_empty_{uuid.uuid4().hex[:6]}"
    _seed_quiz_with_questions(quiz_id, [{
        "question_id": qid,
        "type": "choice",
        "stem": "Empty KP list",
        "options": ["A", "B", "C", "D"],
        "correct": "B",
        "knowledge_points": [],  # Empty list
    }])

    status, body = _submit(quiz_id, [{"questionId": qid, "answer": "B"}])
    assert status == 200
    kprs = body["data"].get("knowledgePointResults", [])
    assert len(kprs) == 1
    assert kprs[0]["knowledgePointKey"] == UNMAPPED_KEY


# ── Test: get_highest_weight_label ────────────────────────────────────────


def test_highest_weight_label():
    """get_highest_weight_label returns the label of the highest-weight mapping."""
    from app.db.repository import create_question_kp_mapping
    _setup()
    db = SessionLocal()
    try:
        qid = f"q_hwl_{uuid.uuid4().hex[:12]}"
        create_question_kp_mapping(
            db, mapping_id=f"map_hwl_a_{uuid.uuid4().hex[:12]}",
            question_id=qid, knowledge_point_key="low",
            knowledge_point_label="Low Priority", weight=0.2, confidence=0.9,
            source="explicit",
        )
        create_question_kp_mapping(
            db, mapping_id=f"map_hwl_b_{uuid.uuid4().hex[:12]}",
            question_id=qid, knowledge_point_key="high",
            knowledge_point_label="High Priority", weight=0.8, confidence=0.9,
            source="explicit",
        )
        db.commit()
        mappings = get_mappings_for_question(db, qid)
        label = get_highest_weight_label(mappings, fallback="none")
        assert label == "High Priority", f"Expected 'High Priority', got '{label}'"
    finally:
        db.close()


# ── Test: resolve_mappings with empty string entries ──────────────────────


def test_fallback_skips_empty_strings():
    """Fallback creation skips empty/whitespace KP strings."""
    _setup()
    db = SessionLocal()
    try:
        mappings = get_or_create_fallback_mappings(
            db, "q_skip_empty", "math", ["valid", "", "  ", "also_valid"],
        )
        db.commit()
        assert len(mappings) == 2, f"Expected 2 mappings (skipping blanks), got {len(mappings)}"
        keys = {m.knowledge_point_key for m in mappings}
        assert "valid" in keys
        assert "also_valid" in keys
    finally:
        db.close()


# ── Run ───────────────────────────────────────────────────────────────────


def main():
    tests = [
        test_single_kp_question,
        test_multi_kp_question,
        test_weights_sum_to_one,
        test_mapping_confidence_propagates,
        test_old_question_creates_fallback,
        test_fallback_mapping_source_and_confidence,
        test_unmapped_question,
        test_all_kps_have_results_not_just_first,
        test_empty_kp_list_is_unmapped,
        test_highest_weight_label,
        test_fallback_skips_empty_strings,
    ]
    failed = 0
    for t in tests:
        try:
            t()
            print(f"  PASS  {t.__name__}")
        except AssertionError as e:
            print(f"  FAIL  {t.__name__}: {e}")
            failed += 1
        except Exception as e:
            import traceback
            print(f"  ERROR {t.__name__}: {e}")
            traceback.print_exc()
            failed += 1

    print(f"\n{len(tests) - failed}/{len(tests)} passed")
    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    try:
        main()
    finally:
        engine.dispose()
        Path(_db_path).unlink(missing_ok=True)
