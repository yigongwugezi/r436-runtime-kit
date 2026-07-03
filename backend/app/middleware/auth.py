"""Auth dependency — injects current learner into request state."""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.db.engine import SessionLocal
from app.db.models import LearnerModel
from app.utils.auth import verify_token

logger = logging.getLogger(__name__)

security = HTTPBearer(auto_error=False)


class AuthContext:
    """Lightweight container for the authenticated learner's context."""

    def __init__(
        self,
        learner_id: str = "",
        role: str = "student",
        learner: Optional[LearnerModel] = None,
    ) -> None:
        self.learner_id = learner_id
        self.role = role
        self.learner = learner

    @property
    def is_authenticated(self) -> bool:
        return bool(self.learner_id)

    @property
    def is_admin(self) -> bool:
        return self.role == "admin"

    @property
    def is_teacher(self) -> bool:
        return self.role in ("teacher", "admin")

    @property
    def is_parent(self) -> bool:
        return self.role == "parent"


async def get_auth(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
) -> AuthContext:
    """Dependency: extract and validate JWT, attach learner to request state.

    If no token is provided, returns an unauthenticated AuthContext.
    Routes that require auth should check ``auth.is_authenticated``.
    """
    if credentials is None:
        return AuthContext()

    token = credentials.credentials
    payload = verify_token(token)
    if payload is None:
        return AuthContext()

    learner_id = payload.get("sub", "")
    role = payload.get("role", "student")

    # Attach to request state for downstream middleware/handlers
    request.state.learner_id = learner_id
    request.state.role = role

    # Optionally load full learner record
    learner = None
    try:
        db = SessionLocal()
        learner = db.get(LearnerModel, learner_id)
    except Exception:
        logger.warning("Failed to load learner %s", learner_id)
    finally:
        try:
            db.close()
        except Exception:
            pass

    return AuthContext(learner_id=learner_id, role=role, learner=learner)


def require_auth(auth: AuthContext = Depends(get_auth)) -> AuthContext:
    """Dependency: require valid authentication.  Raises 401 if missing."""
    if not auth.is_authenticated:
        from fastapi import HTTPException
        raise HTTPException(status_code=401, detail="请先登录")
    return auth


def reject_parent(auth: AuthContext = Depends(require_auth)) -> AuthContext:
    """Dependency: reject requests from parent accounts on write endpoints."""
    if auth.is_parent:
        from fastapi import HTTPException

        raise HTTPException(status_code=403, detail="家长账户无法执行此操作")
    return auth
