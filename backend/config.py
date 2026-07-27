import os
from dotenv import load_dotenv

load_dotenv()

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
DEEPSEEK_BASE_URL = "https://api.deepseek.com"

ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "admin123")

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
