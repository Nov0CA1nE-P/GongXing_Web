import ipaddress
import os
from urllib.parse import urlsplit

from dotenv import load_dotenv
from origin_normalization import normalize_origin

# 测试必须完全依赖调用方预先注入的隔离配置，不能读取项目真实 .env。
_PRESET_APP_ENV = os.getenv("APP_ENV")
if _PRESET_APP_ENV != "test":
    load_dotenv()

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
DEEPSEEK_BASE_URL = "https://api.deepseek.com"
DEEPSEEK_MAX_PROMPT_CHARS = 16000

APP_ENV = os.getenv("APP_ENV")
if APP_ENV not in {"development", "test", "production"}:
    raise RuntimeError(
        "APP_ENV 必须显式设置为 development、test 或 production"
    )


def _is_loopback_host(hostname: str) -> bool:
    if hostname == "localhost":
        return True
    try:
        return ipaddress.ip_address(hostname).is_loopback
    except ValueError:
        return False


def _parse_origin_list(setting_name: str, *, required: bool) -> tuple[str, ...]:
    raw_value = os.getenv(setting_name)
    if raw_value is None or not raw_value.strip():
        if required:
            raise RuntimeError(f"{setting_name} 必须显式配置")
        return ()

    origins: list[str] = []
    for raw_origin in raw_value.split(","):
        candidate = raw_origin.strip()
        if not candidate or candidate == "null" or "*" in candidate:
            raise RuntimeError(f"{setting_name} 包含无效来源")
        origin = normalize_origin(candidate)
        if origin is None:
            raise RuntimeError(f"{setting_name} 只允许精确的 HTTP(S) Origin")

        hostname = urlsplit(origin).hostname
        if hostname is None:
            raise RuntimeError(f"{setting_name} 包含无效来源")
        if APP_ENV == "production":
            if (
                not origin.startswith("https://")
                or _is_loopback_host(hostname)
            ):
                raise RuntimeError(
                    f"{setting_name} 在 production 中只允许 HTTPS 正式来源"
                )
        elif APP_ENV == "development":
            if not _is_loopback_host(hostname):
                raise RuntimeError(
                    f"{setting_name} 在 development 中只允许回环来源"
                )
        elif (
            origin.startswith("http://")
            and not _is_loopback_host(hostname)
        ):
            raise RuntimeError(
                f"{setting_name} 在 test 中的 HTTP 来源必须是回环地址"
            )

        if origin in origins:
            raise RuntimeError(f"{setting_name} 不允许重复来源")
        origins.append(origin)
    return tuple(origins)


TRUSTED_ORIGINS = _parse_origin_list("TRUSTED_ORIGINS", required=True)
CORS_ALLOWED_ORIGINS = _parse_origin_list(
    "CORS_ALLOWED_ORIGINS",
    required=False,
)
if not set(CORS_ALLOWED_ORIGINS).issubset(TRUSTED_ORIGINS):
    raise RuntimeError("CORS_ALLOWED_ORIGINS 必须是 TRUSTED_ORIGINS 的子集")

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

rate_limit_max_buckets_setting = os.getenv("RATE_LIMIT_MAX_BUCKETS", "20000")
try:
    RATE_LIMIT_MAX_BUCKETS = int(rate_limit_max_buckets_setting)
except ValueError as exc:
    raise RuntimeError("RATE_LIMIT_MAX_BUCKETS 必须是整数") from exc

if not 1000 <= RATE_LIMIT_MAX_BUCKETS <= 100000:
    raise RuntimeError(
        "RATE_LIMIT_MAX_BUCKETS 必须介于 1000 和 100000 之间"
    )


def _parse_trusted_proxy_ips() -> tuple[str, ...]:
    raw_value = os.getenv("TRUSTED_PROXY_IPS", "")
    if APP_ENV != "production":
        if raw_value.strip():
            raise RuntimeError(
                "development 和 test 环境必须关闭代理头且不得配置 TRUSTED_PROXY_IPS"
            )
        return ()

    if not raw_value.strip():
        raise RuntimeError("production 环境必须显式配置 TRUSTED_PROXY_IPS")

    addresses: list[str] = []
    for raw_address in raw_value.split(","):
        candidate = raw_address.strip()
        if not candidate or candidate == "*" or "/" in candidate:
            raise RuntimeError("TRUSTED_PROXY_IPS 只允许精确 IP 地址")
        try:
            address = ipaddress.ip_address(candidate).compressed
        except ValueError as exc:
            raise RuntimeError(
                "TRUSTED_PROXY_IPS 只允许精确 IP 地址"
            ) from exc
        if address in addresses:
            raise RuntimeError("TRUSTED_PROXY_IPS 不允许重复地址")
        addresses.append(address)
    return tuple(addresses)


TRUSTED_PROXY_IPS = _parse_trusted_proxy_ips()
UVICORN_PROXY_HEADERS = APP_ENV == "production"

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

def _test_path_override(name: str, default: str) -> str:
    raw_value = os.getenv(name)
    if APP_ENV != "test":
        return default
    if not raw_value:
        return default
    if not os.path.isabs(raw_value):
        raise RuntimeError(f"{name} 在 test 环境中必须是绝对路径")
    return os.path.normpath(raw_value)


# development/production 固定使用项目 data/；test 可在导入前注入隔离路径。
COURSEWARE_DIR = os.path.join(PROJECT_ROOT, "data", "courseware")
UPLOADS_DIR = _test_path_override(
    "UPLOADS_DIR",
    os.path.join(PROJECT_ROOT, "data", "uploads"),
)
COURSEWARE_TEMP_DIR = _test_path_override(
    "COURSEWARE_TEMP_DIR",
    os.path.join(PROJECT_ROOT, "data", "tmp", "courseware"),
)
