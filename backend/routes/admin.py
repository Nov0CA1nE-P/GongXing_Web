import time

from fastapi import APIRouter, Depends, HTTPException, Request, Response
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
from origin_security import require_csrf_token, require_trusted_source

router = APIRouter(prefix="/api/admin", tags=["admin"])


class LoginRequest(BaseModel):
    password: str


@router.post("/login")
def login(credentials: LoginRequest, request: Request, response: Response):
    require_trusted_source(request)
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
        "csrf_token": session.csrf_token,
    }


@router.get("/session")
def get_session(
    response: Response,
    session: AdminSession = Depends(require_admin),
):
    return {
        "authenticated": True,
        "expires_in": max(0, int(session.expires_at - time.time())),
        "csrf_token": session.csrf_token,
    }


@router.post("/logout", status_code=204)
def logout(request: Request):
    response = Response(status_code=204)
    token = request.cookies.get(ADMIN_COOKIE_NAME)
    if not token:
        clear_admin_cookie(response)
        response.headers["Cache-Control"] = "no-store"
        return response

    session = admin_session_store.validate(token)
    if session is None:
        clear_admin_cookie(response)
        response.headers["Cache-Control"] = "no-store"
        return response
    if session.role != "admin":
        raise HTTPException(status_code=403, detail="当前身份无权执行此操作")

    require_trusted_source(request)
    require_csrf_token(request, session.csrf_token)
    admin_session_store.revoke(token)
    clear_admin_cookie(response)
    response.headers["Cache-Control"] = "no-store"
    return response
