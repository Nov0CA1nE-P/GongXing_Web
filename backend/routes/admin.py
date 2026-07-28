import time

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel

from auth import (
    ADMIN_COOKIE_NAME,
    AdminSession,
    admin_session_store,
    clear_admin_cookie,
    require_admin,
    set_admin_cookie,
    verify_admin_password,
)

router = APIRouter(prefix="/api/admin", tags=["admin"])


class LoginRequest(BaseModel):
    password: str


@router.post("/login")
def login(credentials: LoginRequest, request: Request, response: Response):
    verify_admin_password(credentials.password)

    # 同一浏览器再次登录时，仅替换当前 Cookie 对应的旧会话。
    old_token = request.cookies.get(ADMIN_COOKIE_NAME)
    if old_token:
        admin_session_store.revoke(old_token)

    token, session = admin_session_store.create()
    set_admin_cookie(response, token)
    response.headers["Cache-Control"] = "no-store"
    return {
        "authenticated": True,
        "expires_in": max(0, int(session.expires_at - time.time())),
    }


@router.get("/session")
def get_session(
    response: Response,
    session: AdminSession = Depends(require_admin),
):
    return {
        "authenticated": True,
        "expires_in": max(0, int(session.expires_at - time.time())),
    }


@router.post("/logout", status_code=204)
def logout(request: Request):
    response = Response(status_code=204)
    token = request.cookies.get(ADMIN_COOKIE_NAME)
    if token:
        admin_session_store.revoke(token)
    clear_admin_cookie(response)
    response.headers["Cache-Control"] = "no-store"
    return response
