import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db.engine import SessionLocal
from app.db.models import SessionModel
from app.db.repository import get_latest_learning_path, get_latest_profile, get_resources
from app.services import agent_service
from app.services.conversation_state import conversation_store


def assert_true(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def _cleanup(session_ids: list[str]) -> None:
    for session_id in session_ids:
        conversation_store._sessions.pop(session_id, None)
    db = SessionLocal()
    try:
        for session_id in session_ids:
            session = db.get(SessionModel, session_id)
            if session:
                db.delete(session)
        db.commit()
    finally:
        db.close()


def test_generated_data_is_readable_by_session_and_isolated() -> None:
    session_a = "p0_session_a"
    session_b = "p0_session_b"
    sessions = [session_a, session_b]
    conversation_store.enable_db()
    _cleanup(sessions)

    try:
        for session_id in sessions:
            agent_service.run_agents(
                session_id=session_id,
                course_id="data_structures",
                user_message="我是软件工程大二学生，想48小时复习数据结构，为了考试通过，喜欢图解和练习题",
            )

        db = SessionLocal()
        try:
            profile_a = get_latest_profile(db, session_a)
            path_a = get_latest_learning_path(db, session_a)
            resources_a = get_resources(db, session_a)
            profile_b = get_latest_profile(db, session_b)
            path_b = get_latest_learning_path(db, session_b)
            resources_b = get_resources(db, session_b)
        finally:
            db.close()

        assert_true(profile_a is not None, "session A should read generated profile")
        assert_true(path_a is not None, "session A should read generated learning path")
        assert_true(resources_a, "session A should read generated resources")
        assert_true(profile_b is not None, "session B should read generated profile")
        assert_true(path_b is not None, "session B should read generated learning path")
        assert_true(resources_b, "session B should read generated resources")
        expected_profile_keys = {
            "major_background",
            "knowledge_base",
            "learning_goal",
            "cognitive_style",
            "error_patterns",
            "coding_ability",
            "learning_progress",
            "interest_direction",
            "learning_rhythm",
            "self_efficacy",
        }
        dims_a = profile_a.dimensions or []
        dims_b = profile_b.dimensions or []
        assert_true({dim.get("key") for dim in dims_a} == expected_profile_keys, "session A profile snapshot should store 10 dimensions")
        assert_true({dim.get("key") for dim in dims_b} == expected_profile_keys, "session B profile snapshot should store 10 dimensions")
        assert_true(
            all(all(field in dim for field in ("score", "confidence", "explanation", "evidence", "source")) for dim in dims_a),
            "session A profile snapshot should keep structured dimension fields",
        )
        assert_true(
            all(dim.get("source") != "unknown" for dim in dims_a + dims_b),
            "profile snapshots should not persist unknown sources",
        )

        assert_true(path_a.session_id == session_a, "session A path should belong to session A")
        assert_true(path_b.session_id == session_b, "session B path should belong to session B")
        assert_true(path_a.id != path_b.id, "path ids should be session scoped")
        assert_true(path_a.id.startswith(f"path_{session_a}_"), "session A path id should include session id")
        assert_true(path_b.id.startswith(f"path_{session_b}_"), "session B path id should include session id")

        ids_a = {resource.id for resource in resources_a}
        ids_b = {resource.id for resource in resources_b}
        assert_true(ids_a.isdisjoint(ids_b), "resource ids should not overlap across sessions")
        assert_true(
            all(resource.session_id == session_a and resource.id.startswith(f"{session_a}_") for resource in resources_a),
            "session A resources should be scoped to session A",
        )
        assert_true(
            all(resource.session_id == session_b and resource.id.startswith(f"{session_b}_") for resource in resources_b),
            "session B resources should be scoped to session B",
        )
    finally:
        _cleanup(sessions)


if __name__ == "__main__":
    test_generated_data_is_readable_by_session_and_isolated()
    print("PASS session_data_contract_test")
