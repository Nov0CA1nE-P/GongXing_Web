from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from auth import AdminSession, require_admin_write
from database import get_db

router = APIRouter(prefix="/api/guestbook", tags=["guestbook"])


class MessageCreate(BaseModel):
    author: str = "匿名"
    content: str
    parent_id: int | None = None


@router.get("/messages")
def list_messages(page: int = 1, limit: int = 20):
    """获取留言列表（分页），只返回顶级留言"""
    conn = get_db()
    offset = (page - 1) * limit

    # 获取顶级留言总数
    total = conn.execute(
        "SELECT COUNT(*) FROM messages WHERE parent_id IS NULL"
    ).fetchone()[0]

    # 获取顶级留言
    rows = conn.execute(
        "SELECT * FROM messages WHERE parent_id IS NULL ORDER BY created_at DESC LIMIT ? OFFSET ?",
        (limit, offset),
    ).fetchall()

    messages = []
    for row in rows:
        msg = dict(row)
        # 获取回复
        replies = conn.execute(
            "SELECT * FROM messages WHERE parent_id = ? ORDER BY created_at ASC",
            (row["id"],),
        ).fetchall()
        msg["replies"] = [dict(r) for r in replies]
        messages.append(msg)

    conn.close()
    return {"messages": messages, "total": total, "page": page, "limit": limit}


@router.post("/messages")
def create_message(msg: MessageCreate):
    """发表留言或回复"""
    if not msg.content.strip():
        raise HTTPException(status_code=400, detail="内容不能为空")

    conn = get_db()

    # 如果是回复，检查父留言是否存在
    if msg.parent_id:
        parent = conn.execute(
            "SELECT id FROM messages WHERE id = ?", (msg.parent_id,)
        ).fetchone()
        if not parent:
            conn.close()
            raise HTTPException(status_code=404, detail="父留言不存在")

    cursor = conn.execute(
        "INSERT INTO messages (author, content, parent_id) VALUES (?, ?, ?)",
        (msg.author.strip() or "匿名", msg.content.strip(), msg.parent_id),
    )
    conn.commit()
    new_id = cursor.lastrowid
    conn.close()

    return {"id": new_id, "message": "留言成功"}


@router.delete("/messages/{message_id}")
def delete_message(
    message_id: int,
    _admin: AdminSession = Depends(require_admin_write),
):
    """删除留言（管理员功能）"""
    conn = get_db()
    conn.execute("DELETE FROM messages WHERE id = ?", (message_id,))
    conn.commit()
    conn.close()
    return {"message": "删除成功"}


@router.post("/messages/{message_id}/react")
def react_to_message(message_id: int, emoji: str = "👍"):
    """给留言添加表情反应"""
    import json
    valid_emojis = ["👍", "❤️", "😄", "🎉", "😢", "🔥", "💡", "👏"]
    if emoji not in valid_emojis:
        raise HTTPException(status_code=400, detail="无效的表情")

    conn = get_db()
    msg = conn.execute("SELECT id, reactions FROM messages WHERE id = ?", (message_id,)).fetchone()
    if not msg:
        conn.close()
        raise HTTPException(status_code=404, detail="留言不存在")

    try:
        reactions = json.loads(msg["reactions"] or "{}")
    except:
        reactions = {}

    reactions[emoji] = reactions.get(emoji, 0) + 1
    conn.execute(
        "UPDATE messages SET reactions = ? WHERE id = ?",
        (json.dumps(reactions, ensure_ascii=False), message_id),
    )
    conn.commit()
    conn.close()
    return {"reactions": reactions}
