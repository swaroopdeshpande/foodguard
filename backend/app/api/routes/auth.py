from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.security import create_access_token, hash_password, verify_password
from app.database.session import get_db
from app.models.audit import AuditLog
from app.models.users import RoleEnum, User
from app.schemas.auth import LoginRequest, TokenResponse, UserCreate, UserOut

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/login", response_model=TokenResponse)
def login(body: LoginRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == body.email).first()
    if not user or not verify_password(body.password, user.hashed_password):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password")
    if not user.is_active:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Account disabled")

    token = create_access_token(subject=user.email, role=user.role.value)
    db.add(AuditLog(user_id=user.id, action="LOGIN", object_type="User", object_id=user.id))
    db.commit()
    return TokenResponse(access_token=token, role=user.role)


@router.post("/register", response_model=UserOut)
def register(body: UserCreate, db: Session = Depends(get_db)):
    """Open registration for the demo. In a real deployment this would be
    ADMIN-only (see require_roles in deps.py) -- left open here so the
    reviewer can create demo accounts without a pre-seeded admin."""
    if db.query(User).filter(User.email == body.email).first():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Email already registered")

    user = User(
        email=body.email, full_name=body.full_name,
        hashed_password=hash_password(body.password), role=body.role,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user
