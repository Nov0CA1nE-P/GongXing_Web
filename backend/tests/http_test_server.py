"""仅供真实 Uvicorn 验收使用的隔离测试入口。"""

import os
from pathlib import Path


def build_test_app():
    if os.environ.get("APP_ENV") != "test":
        raise RuntimeError("隔离 HTTP 测试入口只允许 APP_ENV=test")

    root_setting = os.environ.get("SUMMERCAMP_TEST_ROOT")
    if not root_setting:
        raise RuntimeError("必须显式配置 SUMMERCAMP_TEST_ROOT")
    root = Path(root_setting).resolve()
    root.mkdir(parents=True, exist_ok=True)

    database_path = root / "site.db"
    uploads_dir = root / "uploads"
    temp_dir = root / "tmp" / "courseware"

    import config

    config.DATABASE_PATH = str(database_path)
    config.UPLOADS_DIR = str(uploads_dir)
    config.COURSEWARE_TEMP_DIR = str(temp_dir)

    import database
    import file_storage
    import routes.courseware as courseware_routes
    import routes.files as files_routes

    database.DATABASE_PATH = str(database_path)
    file_storage.UPLOADS_DIR = str(uploads_dir)
    file_storage.COURSEWARE_TEMP_DIR = str(temp_dir)
    courseware_routes.UPLOADS_DIR = str(uploads_dir)
    courseware_routes.COURSEWARE_TEMP_DIR = str(temp_dir)
    files_routes.UPLOADS_DIR = str(uploads_dir)

    import main

    return main.app


app = build_test_app()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        app,
        host="127.0.0.1",
        port=int(os.environ.get("SUMMERCAMP_TEST_PORT", "8765")),
        proxy_headers=False,
        forwarded_allow_ips="",
        log_level="warning",
    )
