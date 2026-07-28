import os
from dotenv import load_dotenv

load_dotenv()

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
DEEPSEEK_BASE_URL = "https://api.deepseek.com"

APP_ENV = os.getenv("APP_ENV")
if APP_ENV not in {"development", "test", "production"}:
    raise RuntimeError(
        "APP_ENV 必须显式设置为 development、test 或 production"
    )

admin_session_ttl_setting = os.getenv("ADMIN_SESSION_TTL_SECONDS", "7200")
try:
    ADMIN_SESSION_TTL_SECONDS = int(admin_session_ttl_setting)
except ValueError as exc:
    raise RuntimeError("ADMIN_SESSION_TTL_SECONDS 必须是整数") from exc

if not 300 <= ADMIN_SESSION_TTL_SECONDS <= 28800:
    raise RuntimeError(
        "ADMIN_SESSION_TTL_SECONDS 必须介于 300 和 28800 秒之间"
    )

ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "")
_unsafe_admin_passwords = {
    "admin123",
    "change-me",
    "changeme",
    "replace-with-a-strong-password",
    "your-admin-password-here",
    "your_admin_password",
    "your-secure-password",
}
ADMIN_AUTH_CONFIGURED = (
    bool(ADMIN_PASSWORD.strip())
    and len(ADMIN_PASSWORD) >= 12
    and ADMIN_PASSWORD.strip().lower() not in _unsafe_admin_passwords
)

if APP_ENV == "production" and not ADMIN_AUTH_CONFIGURED:
    raise RuntimeError(
        "production 环境必须配置至少 12 个字符且不是示例值的 ADMIN_PASSWORD"
    )

ADMIN_COOKIE_SECURE = APP_ENV == "production"

courseware_max_upload_setting = os.getenv("COURSEWARE_MAX_UPLOAD_MB", "50")
try:
    COURSEWARE_MAX_UPLOAD_MB = int(courseware_max_upload_setting)
except ValueError as exc:
    raise RuntimeError("COURSEWARE_MAX_UPLOAD_MB 必须是整数") from exc

if not 1 <= COURSEWARE_MAX_UPLOAD_MB <= 500:
    raise RuntimeError(
        "COURSEWARE_MAX_UPLOAD_MB 必须介于 1 和 500 之间"
    )

COURSEWARE_MAX_UPLOAD_BYTES = COURSEWARE_MAX_UPLOAD_MB * 1024 * 1024

# 相对数据库路径统一以项目根目录为基准，避免因启动目录不同而写入错误位置。
database_path_setting = os.getenv("DATABASE_PATH", "data/site.db")
if os.path.isabs(database_path_setting):
    DATABASE_PATH = os.path.normpath(database_path_setting)
else:
    DATABASE_PATH = os.path.normpath(
        os.path.join(PROJECT_ROOT, database_path_setting)
    )

# 课件文件存储目录
COURSEWARE_DIR = os.path.join(PROJECT_ROOT, "data", "courseware")
UPLOADS_DIR = os.path.join(PROJECT_ROOT, "data", "uploads")
COURSEWARE_TEMP_DIR = os.path.join(PROJECT_ROOT, "data", "tmp", "courseware")
