from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from origin_normalization import normalize_origin

CORS_METHODS = ["GET", "POST", "PUT", "DELETE"]
CORS_HEADERS = ["Content-Type", "X-CSRF-Token"]


class NormalizedCORSMiddleware(CORSMiddleware):
    def is_allowed_origin(self, origin: str) -> bool:
        normalized = normalize_origin(origin)
        return (
            normalized is not None
            and normalized in self.allow_origins
        )


def configure_cors(app: FastAPI, allowed_origins: tuple[str, ...]) -> None:
    """同域部署不启用 CORS；跨域调试仅使用显式最小白名单。"""
    if not allowed_origins:
        return
    normalized_origins = tuple(
        normalized
        for origin in allowed_origins
        if (normalized := normalize_origin(origin)) is not None
    )
    if len(normalized_origins) != len(allowed_origins):
        raise ValueError("CORS 来源必须是有效的 HTTP(S) Origin")
    app.add_middleware(
        NormalizedCORSMiddleware,
        allow_origins=list(normalized_origins),
        allow_credentials=True,
        allow_methods=CORS_METHODS,
        allow_headers=CORS_HEADERS,
    )
