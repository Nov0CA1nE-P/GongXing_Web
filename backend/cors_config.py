from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

CORS_METHODS = ["GET", "POST", "PUT", "DELETE"]
CORS_HEADERS = ["Content-Type", "X-CSRF-Token"]


def configure_cors(app: FastAPI, allowed_origins: tuple[str, ...]) -> None:
    """同域部署不启用 CORS；跨域调试仅使用显式最小白名单。"""
    if not allowed_origins:
        return
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(allowed_origins),
        allow_credentials=True,
        allow_methods=CORS_METHODS,
        allow_headers=CORS_HEADERS,
    )
