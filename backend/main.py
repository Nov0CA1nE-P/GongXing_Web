from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
import os

from database import init_db
from routes import admin, contact, courseware, guestbook, qanda

# 初始化数据库
init_db()

app = FastAPI(
    title="躬行启杭 - 学军中学交流平台",
    description="北京科技大学躬行启杭专业科普体验实践团",
    version="1.0.0",
)

# CORS 配置（允许前端开发服务器访问）
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册路由
app.include_router(admin.router)
app.include_router(courseware.router)
app.include_router(guestbook.router)
app.include_router(qanda.router)
app.include_router(contact.router)

# 静态文件服务（课件PDF、上传文件）
data_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
os.makedirs(os.path.join(data_dir, "courseware"), exist_ok=True)
os.makedirs(os.path.join(data_dir, "uploads"), exist_ok=True)
app.mount("/data", StaticFiles(directory=data_dir), name="data")


@app.get("/api/health")
def health_check():
    return {"status": "ok", "message": "躬行启杭交流平台运行中"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
