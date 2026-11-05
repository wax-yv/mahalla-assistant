from __future__ import annotations

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.db import get_db
from app.core.deps import enforce_csrf, get_current_session, get_current_user
from app.core.security import SESSION_COOKIE
from app.models import Session as SessionModel
from app.models import User
from app.schemas import LoginRequest, MeResponse, MessageResponse, UserOut
from app.services import auth as auth_service

router = APIRouter(prefix="/auth", tags=["auth"])


def _me(user: User, session: SessionModel) -> MeResponse:
    return MeResponse(
        user=UserOut.model_validate(user),
        csrf_token=session.csrf_token,
        demo_mode=settings.demo_mode,
        version=settings.app_version,
    )


@router.post("/login", response_model=MeResponse)
def login(payload: LoginRequest, request: Request, response: Response, db: Session = Depends(get_db)):
    user = auth_service.authenticate(db, payload.username, payload.password, request)
    token, session = auth_service.create_session(db, user, request)
    db.commit()
    response.set_cookie(
        SESSION_COOKIE,
        token,
        httponly=True,
        secure=settings.is_production,
        samesite="lax",
        max_age=settings.session_ttl_hours * 3600,
        path="/",
    )
    return _me(user, session)


@router.get("/me", response_model=MeResponse)
def me(user: User = Depends(get_current_user), session: SessionModel = Depends(get_current_session)):
    return _me(user, session)


@router.post("/logout", response_model=MessageResponse)
def logout(
    response: Response,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    session: SessionModel = Depends(get_current_session),
):
    enforce_csrf(request, session)
    auth_service.revoke_session(db, session, user.id)
    db.commit()
    response.delete_cookie(SESSION_COOKIE, path="/")
    return MessageResponse(message="Tizimdan chiqdingiz.")
