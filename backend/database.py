import sqlite3
import os
from config import DATABASE_PATH

# 确保数据目录存在
os.makedirs(os.path.dirname(os.path.abspath(DATABASE_PATH)), exist_ok=True)


def get_db():
    """获取数据库连接"""
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db():
    """初始化数据库表"""
    conn = get_db()
    cursor = conn.cursor()

    cursor.executescript("""
        CREATE TABLE IF NOT EXISTS courseware (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            date TEXT NOT NULL,
            description TEXT DEFAULT '',
            tags TEXT DEFAULT '',
            pdf_path TEXT DEFAULT '',
            pptx_path TEXT DEFAULT '',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            author TEXT DEFAULT '匿名',
            content TEXT NOT NULL,
            parent_id INTEGER DEFAULT NULL,
            reactions TEXT DEFAULT '{}',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (parent_id) REFERENCES messages(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS questions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            author TEXT DEFAULT '匿名',
            content TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS answers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            question_id INTEGER NOT NULL,
            content TEXT NOT NULL,
            is_ai_generated INTEGER DEFAULT 0,
            status TEXT DEFAULT 'pending',
            reviewed_by TEXT DEFAULT NULL,
            likes INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (question_id) REFERENCES questions(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS follow_ups (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            question_id INTEGER NOT NULL,
            author TEXT DEFAULT '匿名',
            content TEXT NOT NULL,
            answer_content TEXT DEFAULT '',
            status TEXT DEFAULT 'pending',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (question_id) REFERENCES questions(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS contact_submissions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            contact_info TEXT DEFAULT '',
            message TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)

    # 添加缺失的列（兼容旧数据库）
    try:
        cursor.execute("ALTER TABLE courseware ADD COLUMN tags TEXT DEFAULT ''")
    except:
        pass
    try:
        cursor.execute("ALTER TABLE answers ADD COLUMN likes INTEGER DEFAULT 0")
    except:
        pass
    try:
        cursor.execute("ALTER TABLE messages ADD COLUMN reactions TEXT DEFAULT '{}'")
    except:
        pass

    conn.commit()
    conn.close()


if __name__ == "__main__":
    init_db()
    print("数据库初始化完成")
