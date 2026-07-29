import secrets
from urllib.parse import urlsplit

from fastapi import HTTPException, Request

from config import TRUSTED_ORIGINS

CSRF_HEADER_NAME = "x-csrf-token"


def _raw_header_values(request: Request, name: str) -> list[str]:
    expected = name.lower().encode("ascii")
    return [
        value.decode("latin-1").strip()
        for key, value in request.scope.get("headers", [])
        if key.lower() == expected
    ]


def _reject_untrusted_source() -> None:
    raise HTTPException(status_code=403, detail="请求来源校验失败")


def _origin_from_referer(referer: str) -> str | None:
    try:
        parsed = urlsplit(referer)
        _ = parsed.port
    except ValueError:
        return None
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.fragment
    ):
        return None
    return f"{parsed.scheme}://{parsed.netloc}"


def require_trusted_source(request: Request) -> None:
    """严格验证唯一 Origin；仅在 Origin 缺失时回退到唯一 Referer。"""
    origins = _raw_header_values(request, "origin")
    referers = _raw_header_values(request, "referer")
    if len(origins) > 1 or len(referers) > 1:
        _reject_untrusted_source()

    if origins:
        origin = origins[0]
        if "," in origin or origin == "null" or origin not in TRUSTED_ORIGINS:
            _reject_untrusted_source()
        return

    if len(referers) != 1:
        _reject_untrusted_source()
    referer_origin = _origin_from_referer(referers[0])
    if referer_origin not in TRUSTED_ORIGINS:
        _reject_untrusted_source()


def require_csrf_token(request: Request, expected_token: str) -> None:
    tokens = _raw_header_values(request, CSRF_HEADER_NAME)
    if (
        len(tokens) != 1
        or not tokens[0]
        or not secrets.compare_digest(tokens[0], expected_token)
    ):
        raise HTTPException(status_code=403, detail="CSRF 校验失败")
