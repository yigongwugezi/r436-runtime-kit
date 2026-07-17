"""Diagnosis snapshot query endpoints.

Provides stable read access to persisted diagnosis snapshots for
Profile, Analytics, Resource, and guided-path modules.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from app.db.engine import SessionLocal
from app.middleware.auth import AuthContext, get_auth, require_auth
from app.services.diagnosis_snapshot_service import (
    get_latest_snapshot,
    get_latest_for_session,
    snapshot_to_dto_dict,
    try_get_diagnosis,
)

router = APIRouter(prefix="/diagnosis-snapshots", tags=["diagnosis"])


@router.get("/latest")
def get_latest_snapshot_endpoint(
    session_id: str = Query(default="", alias="sessionId"),
    subject_id: str = Query(default="", alias="subjectId"),
    auth: AuthContext = Depends(require_auth),
) -> dict:
    """Return the latest ready diagnosis snapshot.

    Accepts either:
    - ``sessionId`` — resolves learner + subject from session
    - ``subjectId`` — used with the authenticated learner

    Returns an empty data response when no snapshot exists.
    """
    db = SessionLocal()
    try:
        dto = try_get_diagnosis(
            db,
            learner_id=auth.learner_id,
            subject_id=subject_id or None,
            session_id=session_id or None,
        )
        if dto is None:
            return {
                "status": "success",
                "data": None,
                "message": "No diagnosis snapshot found",
            }
        return {"status": "success", "data": dto}
    finally:
        db.close()


@router.get("/{snapshot_id}")
def get_snapshot_by_id(
    snapshot_id: str,
    auth: AuthContext = Depends(require_auth),
) -> dict:
    """Return a specific diagnosis snapshot by ID.

    The authenticated learner must own the snapshot.
    """
    from app.db.models import DiagnosisSnapshotModel

    db = SessionLocal()
    try:
        snap = db.get(DiagnosisSnapshotModel, snapshot_id)
        if snap is None:
            return {"status": "error", "message": "Snapshot not found"}
        if snap.learner_id != auth.learner_id:
            from fastapi import HTTPException
            raise HTTPException(status_code=403, detail="Forbidden")

        return {"status": "success", "data": snapshot_to_dto_dict(snap)}
    finally:
        db.close()
