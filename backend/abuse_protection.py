import base64
import hashlib
import hmac
import ipaddress
import re
import secrets
from dataclasses import dataclass

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

from config import ADMIN_COOKIE_SECURE, RATE_LIMIT_MAX_BUCKETS
from rate_limit import RateRule, SlidingWindowRateLimiter

VISITOR_COOKIE_NAME = "visitor_rl"
VISITOR_COOKIE_PATH = "/api"
VISITOR_COOKIE_MAX_LENGTH = 96
_VISITOR_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{22}$")
_SIGNATURE_PATTERN = re.compile(r"^[A-Za-z0-9_-]{43}$")

PUBLIC_WRITE_PATHS = (
    re.compile(r"^/api/contact/submit$"),
    re.compile(r"^/api/guestbook/messages$"),
    re.compile(r"^/api/guestbook/messages/\d+/react$"),
    re.compile(r"^/api/qanda/questions$"),
    re.compile(r"^/api/qanda/questions/\d+/follow-ups$"),
    re.compile(r"^/api/qanda/answers/\d+/like$"),
    re.compile(r"^/api/qanda/analyze-personality$"),
)


def _base64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


class VisitorIdentityManager:
    def __init__(self, signing_key: bytes | None = None) -> None:
        self._signing_key = signing_key or secrets.token_bytes(32)

    def _signature(self, visitor_id: str) -> str:
        digest = hmac.new(
            self._signing_key,
            f"v1.{visitor_id}".encode("ascii"),
            hashlib.sha256,
        ).digest()
        return _base64url(digest)

    def create(self) -> tuple[str, str]:
        visitor_id = _base64url(secrets.token_bytes(16))
        cookie = f"v1.{visitor_id}.{self._signature(visitor_id)}"
        return visitor_id, cookie

    def validate(self, cookie: str | None) -> str | None:
        if not cookie or len(cookie) > VISITOR_COOKIE_MAX_LENGTH:
            return None
        try:
            cookie.encode("ascii")
        except UnicodeEncodeError:
            return None
        parts = cookie.split(".")
        if len(parts) != 3 or parts[0] != "v1":
            return None
        visitor_id, signature = parts[1], parts[2]
        if (
            not _VISITOR_ID_PATTERN.fullmatch(visitor_id)
            or not _SIGNATURE_PATTERN.fullmatch(signature)
        ):
            return None
        expected = self._signature(visitor_id)
        if not hmac.compare_digest(signature, expected):
            return None
        return visitor_id


visitor_identity_manager = VisitorIdentityManager()
rate_limiter = SlidingWindowRateLimiter(RATE_LIMIT_MAX_BUCKETS)


def is_public_write_path(method: str, path: str) -> bool:
    return method == "POST" and any(
        pattern.fullmatch(path) for pattern in PUBLIC_WRITE_PATHS
    )


class VisitorIdentityMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if not is_public_write_path(request.method, request.url.path):
            return await call_next(request)

        supplied_cookie = request.cookies.get(VISITOR_COOKIE_NAME)
        visitor_id = visitor_identity_manager.validate(supplied_cookie)
        new_cookie: str | None = None
        if visitor_id is None:
            visitor_id, new_cookie = visitor_identity_manager.create()
        request.state.visitor_id = visitor_id

        response: Response = await call_next(request)
        if new_cookie is not None:
            response.set_cookie(
                key=VISITOR_COOKIE_NAME,
                value=new_cookie,
                path=VISITOR_COOKIE_PATH,
                secure=ADMIN_COOKIE_SECURE,
                httponly=True,
                samesite="strict",
            )
        return response


def client_ip(request: Request) -> str:
    host = request.client.host if request.client else ""
    try:
        address = ipaddress.ip_address(host)
        if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped:
            return address.ipv4_mapped.compressed
        return address.compressed
    except ValueError:
        return "unknown"


@dataclass(frozen=True)
class PublicIdentity:
    visitor_id: str
    ip: str


def public_identity(request: Request) -> PublicIdentity:
    visitor_id = getattr(request.state, "visitor_id", None)
    if not visitor_id:
        raise RuntimeError("公开写接口缺少访客身份中间件")
    return PublicIdentity(visitor_id=visitor_id, ip=client_ip(request))


class RateLimitExceeded(Exception):
    def __init__(self, retry_after: int) -> None:
        self.retry_after = retry_after


def reject_rate_limit(retry_after: int) -> None:
    raise RateLimitExceeded(retry_after)


def check_rules(rules: list[RateRule]) -> None:
    result = rate_limiter.check_many(rules)
    if not result.allowed:
        reject_rate_limit(result.retry_after)


def consume_rules(rules: list[RateRule]) -> None:
    result = rate_limiter.consume_many(rules)
    if not result.allowed:
        reject_rate_limit(result.retry_after)


def rule(
    name: str,
    identity: str,
    limit: int,
    window_seconds: int,
) -> RateRule:
    return RateRule(name, identity, limit, window_seconds)


def visitor_and_ip_rules(
    identity: PublicIdentity,
    name: str,
    *,
    visitor_limits: tuple[tuple[int, int], ...],
    ip_limits: tuple[tuple[int, int], ...],
) -> list[RateRule]:
    rules = [
        rule(f"{name}:visitor:{window}", identity.visitor_id, limit, window)
        for limit, window in visitor_limits
    ]
    rules.extend(
        rule(f"{name}:ip:{window}", identity.ip, limit, window)
        for limit, window in ip_limits
    )
    return rules


AI_GLOBAL_RULES = [
    rule("ai:global:60", "admin-account", 40, 60),
    rule("ai:global:3600", "admin-account", 120, 3600),
    rule("ai:global:86400", "admin-account", 500, 86400),
]

LOGIN_IP_RULE_NAMES = {
    "admin-login:ip:900",
    "admin-login:ip:86400",
}


def login_failure_rules(ip: str) -> list[RateRule]:
    return [
        rule("admin-login:ip:900", ip, 5, 900),
        rule("admin-login:ip:86400", ip, 20, 86400),
        rule("admin-login:global:900", "admin-account", 50, 900),
        rule("admin-login:global:86400", "admin-account", 200, 86400),
    ]


def clear_login_ip_failures(ip: str) -> None:
    rate_limiter.clear(names=LOGIN_IP_RULE_NAMES, identity=ip)
