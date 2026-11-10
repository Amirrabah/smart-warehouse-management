from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.demo import DEMO_PASSWORD, DEMO_USERS
from app.dependencies import get_current_user
from app.models import User
from app.rate_limit import limiter
from app.schemas.auth import DemoAccount, LoginRequest, TokenResponse
from app.schemas.user import UserOut
from app.security import DUMMY_HASH, create_access_token, verify_password

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=TokenResponse)
@limiter.limit("5/minute")
def login(request: Request, data: LoginRequest, db: Annotated[Session, Depends(get_db)]):
    invalid = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid email or password",
    )
    email = data.email.strip().lower()
    user = db.scalar(select(User).where(User.email == email))

    if user is None:
        verify_password(data.password, DUMMY_HASH)
        raise invalid
    if not verify_password(data.password, user.password_hash) or not user.is_active:
        raise invalid

    return TokenResponse(access_token=create_access_token(user.id))


@router.get("/demo-accounts", response_model=list[DemoAccount])
def demo_accounts():
    """The public demo logins shown on the login page. Empty unless DEMO_MODE is on."""
    if not settings.demo_mode:
        return []
    return [
        DemoAccount(role=u.role.value, name=u.name, email=u.email, password=DEMO_PASSWORD)
        for u in DEMO_USERS
    ]


@router.get("/me", response_model=UserOut)
def me(current_user: Annotated[User, Depends(get_current_user)]):
    return current_user
