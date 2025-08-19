

from __future__ import annotations
import os
import json
import jwt
from typing import Annotated
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, Path, Request, HTTPException
from starlette.responses import RedirectResponse
from fastapi.security import HTTPBearer
from fastapi_pagination import Page
from sqlalchemy.orm import Session
from authlib.integrations.starlette_client import OAuth
from app.utils.redis_state_storage import RedisStateStorage
from app.config.base import settings

from app.daos.users import create_user as create_user_dao
from app.daos.users import get_user as get_user_dao
from app.daos.users import login as signin
from app.daos.users import get_user_by_email, create_user

from app.schemas.users.users_request import CreateUser, Login
from app.schemas.users.users_response import UserOutResponse
from app.sessions.db import create_local_session
from app.utils.user_utils import get_current_user
from app.models.users import User

user_router = APIRouter()
httpBearerScheme = HTTPBearer()

# OAuth setup
oauth = OAuth()
oauth.state_storage = RedisStateStorage()

# Register providers
oauth.register(
    name="google",
    client_id=settings.GOOGLE_CLIENT_ID,
    client_secret=settings.GOOGLE_CLIENT_SECRET,
    server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
    client_kwargs={"scope": "openid email profile"},
)

oauth.register(
    name="linkedin",
    client_id=os.getenv("LINKEDIN_CLIENT_ID"),
    client_secret=os.getenv("LINKEDIN_CLIENT_SECRET"),
    access_token_url="https://www.linkedin.com/oauth/v2/accessToken",
    authorize_url="https://www.linkedin.com/oauth/v2/authorization",
    client_kwargs={"scope": "r_liteprofile r_emailaddress"},
)

# ----------------------
# JWT helper
# ----------------------
def generate_jwt(user: User) -> str:
    payload = {
        "user_id": user.id,
        "email": user.email,
        "name": user.name,
        "exp": datetime.utcnow() + timedelta(hours=24),
    }
    token = jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm="HS256")
    return token


# ----------------------
# OAuth Login
# ----------------------
@user_router.get("/auth/login/{provider}", tags=["OAuth"])
async def oauth_login(provider: str, request: Request):
    redirect_uri = request.url_for("oauth_callback", provider=provider)
    client = oauth.create_client(provider)
    if not client:
        return {"Error": f"OAuth client for provider '{provider}' is not registered"}
    try:
        # This generates the provider login URL and sets state in Redis
        return await client.authorize_redirect(request, redirect_uri)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to initiate {provider} login: {e}")


# OAuth Callback
@user_router.get("/auth/callback/{provider}", tags=["OAuth"])
async def oauth_callback(provider: str, request: Request, db: Session = Depends(create_local_session)):
    client = oauth.create_client(provider)
    if not client:
        raise HTTPException(status_code=400, detail=f"Unsupported provider: {provider}")

    token_data = await client.authorize_access_token(request)

    # -------- Google ----------
    if provider == "google":
        user_info = token_data.get("userinfo")
        if not user_info:
            raise HTTPException(status_code=400, detail="Google user info not found")
        email = user_info["email"]
        name = user_info["name"]

    # -------- LinkedIn ----------
    elif provider == "linkedin":
        profile = await client.get("me", token=token_data)
        email_data = await client.get(
            "emailAddress?q=members&projection=(elements*(handle~))",
            token=token_data
        )
        email = email_data.json()["elements"][0]["handle~"]["emailAddress"]
        name = f"{profile.json().get('localizedFirstName')} {profile.json().get('localizedLastName')}"

    else:
        raise HTTPException(status_code=400, detail="Unsupported provider")

    user = get_user_by_email(email=email, provider=provider, db_session=db)
    if not user:
        user = create_user(name=name, email=email, provider=provider, db_session=db)

    token = generate_jwt(user)

    if user.onboarding_completed:
        return RedirectResponse(
            url=f"http://localhost:5173/dashboard?"
                f"token={token}&user_id={user.id}&onboard=true"
        )
    else:
        return RedirectResponse(
            url=f"http://localhost:5173/dashboard?"
                f"token={token}&user_id={user.id}&onboard=false"
        )


# ----------------------
# Onboarding API
# ----------------------
@user_router.post("/onboarding", tags=["Users"])
def complete_onboarding(
    email: str,
    name: str,
    phone: str,
    address: str,
    company: str,
    provider: str,
    db: Session = Depends(create_local_session)
):
    user = db.query(User).filter(User.email == email).first()
    if not user:
        user = User(email=email, name=name, provider=provider)
        db.add(user)

    user.phone = phone
    user.address = address
    user.company = company
    user.onboarding_completed = True
    db.commit()

    token = generate_jwt(user)
    return {
        "message": "Onboarding completed successfully",
        "token": token,
        "user_id": user.id,
        "provider": provider,
        "onboarding_completed": True
    }

