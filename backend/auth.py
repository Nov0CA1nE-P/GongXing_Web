import hashlib
import secrets
import threading
import time
from dataclasses import dataclass, field
from typing import Callable

from fastapi import HTTPException, Request, Response

from config import (
    ADMIN_AUTH_CONFIGURED,
    ADMIN_COOKIE_SECURE,
    ADMIN_PASSWORD,
    ADMIN_SESSION_TTL_SECONDS,
)
from origin_security import require_csrf_token, require_trusted_source

ADMIN_COOKIE_NAME = "admin_session"
ADMIN_COOKIE_PATH = "/api"


@dataclass(frozen=True)
class AdminSession:
    role: str
    expires_at: float
    csrf_token: str = field(repr=False)


class AdminSessionStore:
    """仅适用于单进程后端的线程安全内存会话表。"""

    def __init__(
        self,
        ttl_seconds: int,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self.ttl_seconds = ttl_seconds
        self._clock = clock
        self._sessions: dict[str, AdminSession] = {}
        self._lock = threading.RLock()

    @staticmethod
    def _digest(token: str) -> str:
        return hashlib.sha256(token.encode("utf-8")).hexdigest()

    def _cleanup_expired_locked(self, now: float) -> None:
        expired = [
            digest
            for digest, session in self._sessions.items()
            if session.expires_at <= now
        ]
        for digest in expired:
            del self._sessions[digest]

    def create(self, role: str = "admin") -> tuple[str, AdminSession]:
        token = secrets.token_urlsafe(32)
        now = self._clock()
        session = AdminSession(
            role=role,
            expires_at=now + self.ttl_seconds,
            csrf_token=secrets.token_urlsafe(32),
        )
        with self._lock:
            self._cleanup_expired_locked(now)
            self._sessions[self._digest(token)] = session
        return token, session

    def validate(self, token: str) -> AdminSession | None:
        now = self._clock()
        with self._lock:
            self._cleanup_expired_locked(now)
            return self._sessions.get(self._digest(token))

    def revoke(self, token: str) -> None:
        now = self._clock()
        with self._lock:
            self._cleanup_expired_locked(now)
            self._sessions.pop(self._digest(token), None)

    def count(self) -> int:
        """仅供健康检查和测试使用，不暴露任何会话内容。"""
        now = self._clock()
        with self._lock:
            self._cleanup_expired_locked(now)
            return len(self._sessions)


admin_session_store = AdminSessionStore(ADMIN_SESSION_TTL_SECONDS)


def verify_admin_password(password: str) -> None:
    if not ADMIN_AUTH_CONFIGURED:
        raise HTTPException(
            status_code=503,
            detail="管理员认证未配置",
        )
    if not secrets.compare_digest(password, ADMIN_PASSWORD):
        raise HTTPException(status_code=401, detail="管理员密码错误")


def set_admin_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        key=ADMIN_COOKIE_NAME,
        value=token,
        path=ADMIN_COOKIE_PATH,
        secure=ADMIN_COOKIE_SECURE,
        httponly=True,
        samesite="strict",
    )


def clear_admin_cookie(response: Response) -> None:
    response.delete_cookie(
        key=ADMIN_COOKIE_NAME,
        path=ADMIN_COOKIE_PATH,
        secure=ADMIN_COOKIE_SECURE,
        httponly=True,
        samesite="strict",
    )


def require_admin(request: Request, response: Response) -> AdminSession:
    token = request.cookies.get(ADMIN_COOKIE_NAME)
    if not token:
        raise HTTPException(status_code=401, detail="请先登录管理员账号")

    session = admin_session_store.validate(token)
    if session is None:
        raise HTTPException(status_code=401, detail="登录已失效，请重新登录")
    if session.role != "admin":
        raise HTTPException(status_code=403, detail="当前身份无权执行此操作")

    response.headers["Cache-Control"] = "no-store"
    return session


def require_admin_write(
    request: Request,
    response: Response,
) -> AdminSession:
    session = require_admin(request, response)
    require_trusted_source(request)
    require_csrf_token(request, session.csrf_token)
    return session
