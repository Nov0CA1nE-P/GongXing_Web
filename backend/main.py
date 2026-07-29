from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from abuse_protection import RateLimitExceeded, VisitorIdentityMiddleware
from config import (
    APP_ENV,
    CORS_ALLOWED_ORIGINS,
    TRUSTED_PROXY_IPS,
    UVICORN_PROXY_HEADERS,
)
from cors_config import configure_cors
from database import init_db
from file_storage import prepare_storage
from routes import admin, contact, courseware, files, guestbook, qanda

# 初始化数据库
init_db()
prepare_storage()

app = FastAPI(
    title="躬行启杭 - 学军中学交流平台",
    description="北京科技大学躬行启杭专业科普体验实践团",
    version="1.0.0",
)
app.add_middleware(VisitorIdentityMiddleware)


@app.exception_handler(RateLimitExceeded)
async def rate_limit_exception_handler(
    _request: Request,
    exc: RateLimitExceeded,
) -> JSONResponse:
    return JSONResponse(
        status_code=429,
        content={
            "detail": "请求过于频繁，请稍后再试",
            "code": "rate_limit_exceeded",
            "retry_after": exc.retry_after,
        },
        headers={
            "Retry-After": str(exc.retry_after),
            "Cache-Control": "no-store",
        },
    )

# 正式同域部署无需 CORS；仅在显式配置调试白名单时启用。
configure_cors(app, CORS_ALLOWED_ORIGINS)

# 注册路由
app.include_router(admin.router)
app.include_router(courseware.router)
app.include_router(guestbook.router)
app.include_router(qanda.router)
app.include_router(contact.router)
app.include_router(files.router)


@app.get("/api/health")
def health_check():
    return {"status": "ok", "message": "躬行启杭交流平台运行中"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8000,
        proxy_headers=UVICORN_PROXY_HEADERS,
        forwarded_allow_ips=",".join(TRUSTED_PROXY_IPS),
    )
