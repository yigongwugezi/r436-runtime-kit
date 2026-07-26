"""Create a disposable, deterministic database for browser QA.

Usage: python backend/scripts/seed_browser_qa.py --db .qa/runtime/run/qa.db
The caller supplies a unique path; this script never discovers or touches a
normal development database.
"""

from __future__ import annotations

import argparse
import json
import os
import secrets
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


IDS = {
    "learner": "qa-learner", "subject": "qa-data-structures", "session": "qa-session",
    "path": "qa-path", "quiz": "qa-quiz", "mindmap": "qa-mindmap", "video": "qa-video",
}


def seed(db_path: Path) -> dict[str, object]:
    db_path = db_path.resolve()
    if db_path.suffix != ".db" or ".qa" not in db_path.parts:
        raise ValueError("QA database must be a .db file under .qa")
    db_path.parent.mkdir(parents=True, exist_ok=True)
    if db_path.exists():
        db_path.unlink()
    os.environ["EDUAGENT_SKIP_ENV_FILE"] = "1"
    os.environ["DATABASE_URL"] = f"sqlite:///{db_path.as_posix()}"
    os.environ.setdefault("LLM_PROVIDER", "mock")
    os.environ.setdefault("RAG_ENABLED", "false")

    from app.db import SessionLocal, init_db
    from app.db.models import (CurrentLearningPathModel, LearnerModel, PersonalSubjectModel,
                               PracticeQuestionModel, QuizModel, ResourceModel)
    from app.db.repository import get_or_create_session, upsert_learning_path
    from app.routers.assessment import _semantic_question_id, _task_quiz_identity, _task_quiz_questions
    from app.utils.auth import hash_password

    init_db()
    days = [
        {"id": "qa-day-read", "globalDayIndex": 1, "progressStatus": "current", "tasks": [{"id": "qa-stage_d1_a", "type": "read_doc", "title": "Reading", "status": "available"}]},
        {"id": "qa-day-quiz", "globalDayIndex": 2, "progressStatus": "current", "tasks": [{"id": "qa-stage_d2_a", "type": "quiz_prac", "title": "Quiz", "status": "available"}]},
        {"id": "qa-day-video", "globalDayIndex": 3, "progressStatus": "current", "tasks": [{"id": "qa-stage_d3_a", "type": "video", "title": "Video", "status": "available"}]},
        {"id": "qa-day-mindmap", "globalDayIndex": 4, "progressStatus": "current", "tasks": [{"id": "qa-stage_d4_a", "type": "mindmap", "title": "Mind map", "status": "available"}]},
    ]
    completed_before = {"quiz-retake": 1, "video-fallback": 2, "mindmap": 3}.get(os.getenv("EDUAGENT_QA_SCENARIO"), 0)
    for index, day in enumerate(days, 1):
        if index <= completed_before:
            day["progressStatus"] = "completed"
            day["tasks"][0]["status"] = "completed"
        elif index > completed_before + 1:
            day["progressStatus"] = "locked"
    path_data = {
        "id": IDS["path"], "subject_id": IDS["subject"], "course_name": "Data Structures",
        "estimatedDays": 4, "stages": [{"id": "qa-stage", "title": "QA fixtures", "days": days}],
        "pending_revision": {"revision_id": "qa-zero-diff", "status": "ready_for_review", "path_id": IDS["path"], "subject_id": IDS["subject"], "diff": {"changed_stages": [], "changed_tasks": [], "total_duration_change": 0}},
    }
    db = SessionLocal()
    try:
        password = secrets.token_urlsafe(24)
        db.add(LearnerModel(id=IDS["learner"], nickname="Browser QA", phone="13900000000", password_hash=hash_password(password), role="student"))
        db.commit()
        db.add(PersonalSubjectModel(id=IDS["subject"], learner_id=IDS["learner"], name="Data Structures"))
        db.commit()
        get_or_create_session(db, IDS["session"], learner_id=IDS["learner"], subject_id=IDS["subject"])
        path = upsert_learning_path(db, IDS["session"], path_data)
        quiz_entry = {"task": days[1]["tasks"][0], "stage_id": "qa-stage", "day_id": "qa-day-quiz", "global_day_index": 2}
        fingerprint, snapshot = _task_quiz_identity(path, quiz_entry, IDS["learner"], IDS["subject"])
        task_quiz_id = f"quiz_{fingerprint[:48]}"
        task_questions = _task_quiz_questions(quiz_entry["task"], quiz_entry["task"]["id"])
        db.add(QuizModel(id=task_quiz_id, title="QA task quiz", session_id=IDS["session"], scope_type="section", scope_id=quiz_entry["task"]["id"], path_id=path.id, stage_id="qa-stage", section_id=quiz_entry["task"]["id"], question_count=5, questions={"semanticFingerprint": fingerprint, "generationVersion": 2, "taskSemanticSnapshot": snapshot, "passingScore": 60}, source="learning_path_task"))
        task_answer_fixture = {}
        for index, question in enumerate(task_questions, 1):
            question_id = _semantic_question_id(fingerprint, index, question["stem"])
            task_answer_fixture[question_id] = question["correct"]
            db.add(PracticeQuestionModel(question_id=question_id, question_set_id=task_quiz_id, session_id=IDS["session"], stem=question["stem"], options=question["options"], correct=question["correct"], explanation=question["explanation"], type="choice"))
        db.add(CurrentLearningPathModel(learner_id=IDS["learner"], session_id=IDS["session"], subject_id=IDS["subject"], path_id=path.id))
        db.add_all([
            ResourceModel(id="qa-reading", session_id=IDS["session"], learner_id=IDS["learner"], subject_id=IDS["subject"], path_id=path.id, type="lecture", title="QA reading", content="# Reading\nFixture content", related_section_id="qa-stage_d1_a", task_id="qa-stage_d1_a"),
            ResourceModel(id=IDS["video"], session_id=IDS["session"], learner_id=IDS["learner"], subject_id=IDS["subject"], path_id=path.id, type="video", title="QA video", content="https://example.invalid/qa-video", related_section_id="qa-stage_d3_a", task_id="qa-stage_d3_a", resource_metadata={"deliveryMode": "video", "fallback": "qa-reading"}),
            ResourceModel(id=IDS["mindmap"], session_id=IDS["session"], learner_id=IDS["learner"], subject_id=IDS["subject"], path_id=path.id, type="mindmap", title="QA mind map", format="graph_data", related_section_id="qa-stage_d4_a", task_id="qa-stage_d4_a", mermaid_def="mindmap\n  root((Data Structures))\n    Arrays\n      Search\n      Insert\n    Trees\n      Traverse\n      Balance"),
        ])
        questions = []
        for index, correct in enumerate("ABCDE", 1):
            qid = f"qa-q{index}"
            questions.append({"question_id": qid, "type": "choice", "stem_abbr": f"Question {index}"})
            db.add(PracticeQuestionModel(question_id=qid, question_set_id=IDS["quiz"], session_id=IDS["session"], stem=f"Question {index}", options={"A": "A", "B": "B", "C": "C", "D": "D", "E": "E"}, correct=correct, explanation="Deterministic QA fixture"))
        db.add(QuizModel(id=IDS["quiz"], title="QA Quiz", session_id=IDS["session"], scope_type="path", scope_id=path.id, path_id=path.id, question_count=5, questions=questions, source="rule_based_fallback"))
        db.commit()
    finally:
        db.close()
    metadata = {
        "databasePath": str(db_path), "learnerId": IDS["learner"], "subjectId": IDS["subject"],
        "sessionId": IDS["session"], "pathId": IDS["path"], "readDocTaskId": "qa-stage_d1_a",
        "quizTaskId": "qa-stage_d2_a", "videoTaskId": "qa-stage_d3_a", "mindMapTaskId": "qa-stage_d4_a",
        "quizAnswers": {"correct": task_answer_fixture, "firstRound": {question_id: (answer if index < 2 else next(option for option in "ABCD" if option != answer)) for index, (question_id, answer) in enumerate(task_answer_fixture.items())}},
        "zeroDiffRevisionId": "qa-zero-diff", "scenarios": ["path", "quiz", "video", "mindmap", "zero-diff-revision"],
    }
    metadata_path = db_path.parent / "seed-metadata.json"
    metadata_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    (db_path.parent / "auth-runtime.json").write_text(json.dumps({"phone": "13900000000", "password": password}), encoding="utf-8")
    return {"database": str(db_path), "metadata": str(metadata_path), "ids": IDS, "scenarios": metadata["scenarios"]}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", required=True, type=Path)
    print(json.dumps(seed(parser.parse_args().db), ensure_ascii=False))


if __name__ == "__main__":
    main()
