"""Repository layer data isolation and upsert tests.

Validates that:
- All resource operations are scoped by session_id.
- Different sessions cannot read/modify/delete each other's data.
- upsert_resource and upsert_learning_path create-then-update correctly.
- update_resource_study_status commits properly.
- list_sessions supports optional learner_id filter.
- Batch operations use synchronize_session='fetch'.

Usage::

    cd backend
    python -m pytest tests/repository_test.py -v
"""

import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest

from app.db import init_db
from app.db.engine import SessionLocal
from app.db.models import LearnerModel, SessionModel
from app.db.repository import (
    batch_set_bookmark,
    batch_update_study_status,
    delete_resource,
    get_bookmarked_ids,
    get_resource,
    get_resources,
    list_sessions,
    toggle_bookmark,
    update_resource_study_status,
    upsert_learning_path,
    upsert_resource,
)

init_db()

# ── helpers ──────────────────────────────────────────────────────────────────


def _uid() -> str:
    return uuid.uuid4().hex[:12]


def _cleanup(db, session_ids: list[str]) -> None:
    """Delete test sessions (cascade deletes their children)."""
    for sid in session_ids:
        sess = db.get(SessionModel, sid)
        if sess:
            db.delete(sess)
    db.commit()


# ── session isolation tests ─────────────────────────────────────────────────


class TestResourceSessionIsolation:
    """All single-resource operations must reject cross-session access."""

    def test_get_resource_session_isolation(self):
        """get_resource with wrong session_id returns None."""
        sid_a = f"iso_get_a_{_uid()}"
        sid_b = f"iso_get_b_{_uid()}"
        db = SessionLocal()
        try:
            rid = f"res_get_{_uid()}"
            upsert_resource(db, sid_a, {"id": rid, "title": "Session A resource"})
            # Same resource id should NOT be visible from session B
            assert get_resource(db, sid_b, rid) is None
            # But IS visible from session A
            found = get_resource(db, sid_a, rid)
            assert found is not None
            assert found.title == "Session A resource"
        finally:
            _cleanup(db, [sid_a, sid_b])
            db.close()

    def test_delete_resource_session_isolation(self):
        """delete_resource with wrong session_id does nothing."""
        sid_a = f"iso_del_a_{_uid()}"
        sid_b = f"iso_del_b_{_uid()}"
        db = SessionLocal()
        try:
            rid = f"res_del_{_uid()}"
            upsert_resource(db, sid_a, {"id": rid, "title": "Keep me"})
            # Attempt delete from session B — should fail (return False)
            assert delete_resource(db, sid_b, rid) is False
            # Resource should still exist in session A
            assert get_resource(db, sid_a, rid) is not None
            # Delete from session A — should succeed
            assert delete_resource(db, sid_a, rid) is True
            assert get_resource(db, sid_a, rid) is None
        finally:
            _cleanup(db, [sid_a, sid_b])
            db.close()

    def test_update_resource_study_status_isolation(self):
        """update_resource_study_status with wrong session_id does nothing."""
        sid_a = f"iso_upd_a_{_uid()}"
        sid_b = f"iso_upd_b_{_uid()}"
        db = SessionLocal()
        try:
            rid = f"res_upd_{_uid()}"
            upsert_resource(db, sid_a, {"id": rid, "study_status": "new"})
            # Attempt update from session B — should return False
            assert update_resource_study_status(db, sid_b, rid, "completed") is False
            # Resource A's status should be unchanged
            found = get_resource(db, sid_a, rid)
            assert found.study_status == "new"
            # Update from session A — should succeed
            assert update_resource_study_status(db, sid_a, rid, "completed") is True
            found = get_resource(db, sid_a, rid)
            assert found.study_status == "completed"
            assert found.completed_at is not None
        finally:
            _cleanup(db, [sid_a, sid_b])
            db.close()

    def test_update_resource_study_status_commit(self):
        """Status change survives across DB sessions (validates db.commit() fix)."""
        sid = f"iso_commit_{_uid()}"
        rid = f"res_commit_{_uid()}"

        db1 = SessionLocal()
        try:
            upsert_resource(db1, sid, {"id": rid, "study_status": "new"})
        finally:
            db1.close()

        # Update in a separate session
        db2 = SessionLocal()
        try:
            assert update_resource_study_status(db2, sid, rid, "in_progress") is True
        finally:
            db2.close()

        # Read in yet another session — change must be persisted
        db3 = SessionLocal()
        try:
            found = get_resource(db3, sid, rid)
            assert found is not None
            assert found.study_status == "in_progress"
        finally:
            _cleanup(db3, [sid])
            db3.close()

    def test_toggle_bookmark_session_isolation(self):
        """toggle_bookmark with wrong session_id returns None."""
        sid_a = f"iso_bm_a_{_uid()}"
        sid_b = f"iso_bm_b_{_uid()}"
        db = SessionLocal()
        try:
            rid = f"res_bm_{_uid()}"
            upsert_resource(db, sid_a, {"id": rid, "bookmarked": False})
            # Toggle from session B — should return None (not found in that session)
            assert toggle_bookmark(db, sid_b, rid) is None
            # Resource A's bookmark should be unchanged
            found = get_resource(db, sid_a, rid)
            assert found.bookmarked is False
            # Toggle from session A — should succeed
            result = toggle_bookmark(db, sid_a, rid)
            assert result is True
            found = get_resource(db, sid_a, rid)
            assert found.bookmarked is True
        finally:
            _cleanup(db, [sid_a, sid_b])
            db.close()

    def test_resource_not_found_returns_none(self):
        """Nonexistent session+resource returns None, doesn't raise."""
        db = SessionLocal()
        try:
            assert get_resource(db, "nonexistent_session", "nonexistent_id") is None
            assert delete_resource(db, "nonexistent_session", "nonexistent_id") is False
            assert update_resource_study_status(db, "nonexistent_session", "nonexistent_id", "completed") is False
            assert toggle_bookmark(db, "nonexistent_session", "nonexistent_id") is None
        finally:
            db.close()


# ── list_sessions learner filter ─────────────────────────────────────────────


class TestListSessionsLearnerFilter:
    def test_list_sessions_learner_filter(self):
        """learner_id filters to a single learner; omitting returns all."""
        db = SessionLocal()
        try:
            lid_a = f"lrn_a_{_uid()}"
            lid_b = f"lrn_b_{_uid()}"
            sid_a = f"sess_a_{_uid()}"
            sid_b = f"sess_b_{_uid()}"

            # Create learners and sessions directly
            la = LearnerModel(id=lid_a, nickname="Learner A")
            lb = LearnerModel(id=lid_b, nickname="Learner B")
            db.add_all([la, lb])
            db.flush()
            sa = SessionModel(id=sid_a, learner_id=lid_a, status="active")
            sb = SessionModel(id=sid_b, learner_id=lid_b, status="active")
            db.add_all([sa, sb])
            db.commit()

            # With learner_id filter — only one session
            result_a = list_sessions(db, status="active", learner_id=lid_a)
            assert len(result_a) == 1
            assert result_a[0].id == sid_a

            # Without learner_id — both sessions (backward compat)
            result_all = list_sessions(db, status="active")
            assert len(result_all) >= 2
            ids = {s.id for s in result_all}
            assert sid_a in ids
            assert sid_b in ids
        finally:
            _cleanup(db, [sid_a, sid_b])
            for lid in [lid_a, lid_b]:
                learner = db.get(LearnerModel, lid)
                if learner:
                    db.delete(learner)
            db.commit()
            db.close()


# ── upsert behaviour tests ──────────────────────────────────────────────────


class TestUpsertBehaviour:
    def test_upsert_resource_creates_and_updates(self):
        """First call creates; second call with same id updates in place."""
        sid = f"upsert_s_{_uid()}"
        rid = f"res_upsert_{_uid()}"
        db = SessionLocal()
        try:
            # Create
            r1 = upsert_resource(db, sid, {
                "id": rid,
                "title": "Original Title",
                "type": "lecture",
                "difficulty": "easy",
                "study_status": "new",
            })
            assert r1.title == "Original Title"
            assert r1.difficulty == "easy"

            # Update — same id, different fields
            r2 = upsert_resource(db, sid, {
                "id": rid,
                "title": "Updated Title",
                "type": "quiz",
                "difficulty": "hard",
                "study_status": "completed",
            })
            assert r2.id == rid
            assert r2.title == "Updated Title"
            assert r2.type == "quiz"
            assert r2.difficulty == "hard"
            assert r2.study_status == "completed"

            # Verify only one row exists
            all_res = get_resources(db, sid)
            assert len([r for r in all_res if r.id == rid]) == 1
        finally:
            _cleanup(db, [sid])
            db.close()

    def test_upsert_learning_path_creates_and_updates(self):
        """First call creates; second call with same id updates in place."""
        sid = f"upsert_lp_{_uid()}"
        pid = f"path_{sid}"
        db = SessionLocal()
        try:
            # Create
            lp1 = upsert_learning_path(db, sid, {
                "id": pid,
                "course_id": "ai_intro",
                "course_name": "AI Intro",
                "estimatedDays": 7,
                "overallProgress": 0,
            })
            assert lp1.course_name == "AI Intro"
            assert lp1.estimated_days == 7

            # Update — same id, different values
            lp2 = upsert_learning_path(db, sid, {
                "id": pid,
                "course_id": "data_structures",
                "course_name": "Data Structures",
                "estimatedDays": 14,
                "overallProgress": 50,
            })
            assert lp2.id == pid
            assert lp2.course_name == "Data Structures"
            assert lp2.course_id == "data_structures"
            assert lp2.estimated_days == 14
            assert lp2.overall_progress == 50
        finally:
            _cleanup(db, [sid])
            db.close()

    def test_upsert_resource_different_sessions_independent(self):
        """Resources from different sessions don't leak via get_resources."""
        sid_a = f"up_ind_a_{_uid()}"
        sid_b = f"up_ind_b_{_uid()}"
        rid_a = f"res_a_{_uid()}"
        rid_b = f"res_b_{_uid()}"
        db = SessionLocal()
        try:
            upsert_resource(db, sid_a, {"id": rid_a, "title": "Resource A"})
            upsert_resource(db, sid_b, {"id": rid_b, "title": "Resource B"})
            # Each session only sees its own resources
            res_a = get_resources(db, sid_a)
            res_b = get_resources(db, sid_b)
            assert len(res_a) == 1
            assert res_a[0].title == "Resource A"
            assert len(res_b) == 1
            assert res_b[0].title == "Resource B"
            # Cross-access blocked
            assert get_resource(db, sid_b, rid_a) is None
            assert get_resource(db, sid_a, rid_b) is None
        finally:
            _cleanup(db, [sid_a, sid_b])
            db.close()


# ── batch operations ────────────────────────────────────────────────────────


class TestBatchOperations:
    def test_batch_update_study_status_scoped(self):
        """Batch update only affects resources in the correct session."""
        sid_a = f"batch_a_{_uid()}"
        sid_b = f"batch_b_{_uid()}"
        rid_a1 = f"batch_ar1_{_uid()}"
        rid_a2 = f"batch_ar2_{_uid()}"
        rid_b1 = f"batch_br1_{_uid()}"
        db = SessionLocal()
        try:
            upsert_resource(db, sid_a, {"id": rid_a1, "study_status": "new"})
            upsert_resource(db, sid_a, {"id": rid_a2, "study_status": "new"})
            upsert_resource(db, sid_b, {"id": rid_b1, "study_status": "new"})

            # Batch update only session A
            count = batch_update_study_status(db, sid_a, [rid_a1, rid_a2], "completed")
            assert count == 2

            # Session A resources updated
            assert get_resource(db, sid_a, rid_a1).study_status == "completed"
            assert get_resource(db, sid_a, rid_a2).study_status == "completed"
            # Session B resource unchanged
            assert get_resource(db, sid_b, rid_b1).study_status == "new"
        finally:
            _cleanup(db, [sid_a, sid_b])
            db.close()

    def test_batch_set_bookmark_scoped(self):
        """Batch bookmark only affects resources in the correct session."""
        sid_a = f"batch_bm_a_{_uid()}"
        sid_b = f"batch_bm_b_{_uid()}"
        rid_a = f"batch_bma_{_uid()}"
        rid_b = f"batch_bmb_{_uid()}"
        db = SessionLocal()
        try:
            upsert_resource(db, sid_a, {"id": rid_a, "bookmarked": False})
            upsert_resource(db, sid_b, {"id": rid_b, "bookmarked": False})

            # Update only session A
            batch_set_bookmark(db, sid_a, [rid_a], True)

            assert get_resource(db, sid_a, rid_a).bookmarked is True
            # Session B resource unchanged
            assert get_resource(db, sid_b, rid_b).bookmarked is False
        finally:
            _cleanup(db, [sid_a, sid_b])
            db.close()

    def test_get_bookmarked_ids_scoped(self):
        """Bookmarked IDs are only from the specified session."""
        sid_a = f"bmid_a_{_uid()}"
        sid_b = f"bmid_b_{_uid()}"
        rid_a = f"bmid_r1_{_uid()}"
        rid_b = f"bmid_r2_{_uid()}"
        db = SessionLocal()
        try:
            upsert_resource(db, sid_a, {"id": rid_a, "bookmarked": True})
            upsert_resource(db, sid_b, {"id": rid_b, "bookmarked": True})

            bm_a = get_bookmarked_ids(db, sid_a)
            assert rid_a in bm_a
            assert rid_b not in bm_a

            bm_b = get_bookmarked_ids(db, sid_b)
            assert rid_b in bm_b
            assert rid_a not in bm_b
        finally:
            _cleanup(db, [sid_a, sid_b])
            db.close()


# ── run ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
