
import json
import jwt
from datetime import datetime, timedelta , timezone
from werkzeug.security import check_password_hash
from sqlalchemy.orm import Session
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from fastapi import HTTPException, Depends

from app.config.base import settings
from app.constants.messages.users import user_messages as messages
from app.models import User
from app.schemas.users.users_request import CreateUser, Login
from app.utils.user_utils import check_existing_field, response_formatter
# from app.sessions.db import get_db
from app.wrappers.cache_wrappers import CacheUtils

def create_jwt(user_id: int):
    expire_minutes = int(str(settings.ACCESS_TOKEN_EXPIRE_MINUTES).strip())
    expire = datetime.utcnow() + timedelta(minutes=expire_minutes)

    payload = {"sub": str(user_id), "exp": int(expire.timestamp())}
    return jwt.encode(payload, str(settings.SECRET_KEY), algorithm=settings.ALGORITHM)

# ----------------------
# Synchronous DAO functions
# ----------------------
# def get_user_by_email(email: str, db_session: Session) -> User | None:
#     return db_session.query(User).filter(User.email == email).first()
def get_user_by_email(email: str, provider: str, db_session: Session) -> User | None:
    return db_session.query(User).filter(User.email == email, User.provider == provider).first()

def create_user(name: str, email: str, provider:str, db_session: Session) -> User:
    user = User(name=name, email=email,provider=provider, onboarding_completed=False)
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user

def oauth_login(email: str, name: str, provider:str, db_session: Session):
    user = get_user_by_email(email, db_session)  # No await needed
    if not user:
        user = create_user(name=name, email=email, provider=provider, db_session=db_session)
    token = create_jwt(user.id)
    return {
        "token": token,
        "user_id": user.id,
        "onboarding_completed": user.onboarding_completed
    }
    
def get_user(user_id: int, db_session: Session):
    if not user_id:
        raise HTTPException(status_code=404, detail=messages["NO_USER_ID_PROVIDED"])

    cache_key = f"user_{user_id}"
    cached_user, _ = CacheUtils.retrieve_cache(cache_key)
    if cached_user:
        return json.loads(cached_user)

    user = db_session.query(
        User.id,
        User.name,
        User.email,
        User.mobile,
        User.created_at,
        User.updated_at,
        User.deleted_at
    ).filter(User.id == user_id).first()

    if not user:
        raise HTTPException(status_code=404, detail=messages["NO_USER_FOUND_FOR_ID"])

    user_dict = dict(user._asdict())
    CacheUtils.create_cache(json.dumps(user_dict, default=str), cache_key, 60)
    return user_dict

def create_user_with_schema(data: CreateUser, db_session: Session):
    user_data = data.dict()

    if check_existing_field(db_session, User, "email", user_data["email"]):
        raise HTTPException(status_code=400, detail=messages["EMAIL_ALREADY_EXIST"])
    if check_existing_field(db_session, User, "mobile", user_data["mobile"]):
        raise HTTPException(status_code=400, detail=messages["MOBILE_ALREADY_EXIST"])

    user = User(**user_data)
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)

    return response_formatter(messages["CREATED_SUCCESSFULLY"])

def login(data: Login, db_session: Session):
    user_data = data.dict()
    user_details = db_session.query(User).filter(User.email == user_data["email"]).first()

    if not user_details:
        raise HTTPException(status_code=404, detail=messages["NO_USERS_FOUND_IN_DB"])
    if not check_password_hash(user_details.password, user_data["password"]):
        raise HTTPException(status_code=400, detail=messages["INVALID_CREDENTIALS"])

    token = create_jwt(user_details.id)
    return response_formatter(messages["LOGIN_SUCCESSFULLY"], {"token": token})