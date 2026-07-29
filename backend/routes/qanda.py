from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from auth import AdminSession, require_admin, require_admin_write
from database import get_db
from services.ai_service import ask_deepseek

router = APIRouter(prefix="/api/qanda", tags=["qanda"])


class QuestionCreate(BaseModel):
    author: str = "匿名"
    content: str


class AnswerReview(BaseModel):
    status: str  # "published" 或 "rejected"
    content: str | None = None  # 管理员修改后的内容（可选）


class FollowUpCreate(BaseModel):
    author: str = "匿名"
    content: str


class FollowUpReview(BaseModel):
    status: str


@router.get("/questions")
def list_questions(page: int = 1, limit: int = 20):
    """获取公开问题列表，只返回已发布的问题。"""
    conn = get_db()
    offset = (page - 1) * limit

    total = conn.execute(
        """SELECT COUNT(DISTINCT q.id) FROM questions q
           JOIN answers a ON a.question_id = q.id
           WHERE a.status = 'published'"""
    ).fetchone()[0]

    rows = conn.execute(
        """SELECT q.*, a.content as answer_content, a.id as answer_id, a.status as answer_status, a.likes as answer_likes
           FROM questions q
           JOIN answers a ON a.question_id = q.id
           WHERE a.status = 'published'
           ORDER BY a.likes DESC, q.created_at DESC LIMIT ? OFFSET ?""",
        (limit, offset),
    ).fetchall()

    questions = []
    for row in rows:
        q = {
            "id": row["id"],
            "author": row["author"],
            "content": row["content"],
            "created_at": row["created_at"],
            "answer": {
                "id": row["answer_id"],
                "content": row["answer_content"],
                "status": row["answer_status"],
                "likes": row["answer_likes"] or 0,
            },
        }
        questions.append(q)

    conn.close()
    return {"questions": questions, "total": total, "page": page, "limit": limit}


@router.post("/questions")
async def create_question(q: QuestionCreate):
    """学生提交问题，自动触发AI回答"""
    if not q.content.strip():
        raise HTTPException(status_code=400, detail="问题内容不能为空")

    conn = get_db()

    # 插入问题
    cursor = conn.execute(
        "INSERT INTO questions (author, content) VALUES (?, ?)",
        (q.author.strip() or "匿名", q.content.strip()),
    )
    question_id = cursor.lastrowid
    conn.commit()

    # 调用AI生成回答
    ai_answer = await ask_deepseek(q.content.strip())

    # 保存AI回答（状态为pending待审核）
    conn.execute(
        "INSERT INTO answers (question_id, content, is_ai_generated, status) VALUES (?, ?, 1, 'pending')",
        (question_id, ai_answer),
    )
    conn.commit()
    conn.close()

    return {
        "id": question_id,
        "message": "问题已提交，AI正在生成回答，请等待审核后查看",
    }


@router.get("/questions/pending")
def list_pending(
    _admin: AdminSession = Depends(require_admin),
):
    """管理员查看待审核的问答"""
    conn = get_db()
    rows = conn.execute(
        """SELECT q.*, a.content as answer_content, a.id as answer_id
           FROM questions q
           JOIN answers a ON a.question_id = q.id
           WHERE a.status = 'pending'
           ORDER BY q.created_at DESC"""
    ).fetchall()
    conn.close()

    return [
        {
            "id": row["id"],
            "author": row["author"],
            "content": row["content"],
            "created_at": row["created_at"],
            "answer": {
                "id": row["answer_id"],
                "content": row["answer_content"],
            },
        }
        for row in rows
    ]


@router.put("/answers/{answer_id}/review")
def review_answer(
    answer_id: int,
    review: AnswerReview,
    _admin: AdminSession = Depends(require_admin_write),
):
    """管理员审核回答"""
    if review.status not in ("published", "rejected"):
        raise HTTPException(status_code=400, detail="状态只能为 published 或 rejected")

    conn = get_db()
    answer = conn.execute(
        "SELECT * FROM answers WHERE id = ?", (answer_id,)
    ).fetchone()
    if not answer:
        conn.close()
        raise HTTPException(status_code=404, detail="回答不存在")

    # 如果管理员修改了内容，用修改后的
    content = review.content if review.content else answer["content"]

    conn.execute(
        "UPDATE answers SET status = ?, content = ?, reviewed_by = 'admin' WHERE id = ?",
        (review.status, content, answer_id),
    )
    conn.commit()
    conn.close()

    return {"message": f"审核完成，状态：{review.status}"}


@router.delete("/questions/{question_id}")
def delete_question(
    question_id: int,
    _admin: AdminSession = Depends(require_admin_write),
):
    """删除问题及关联回答"""
    conn = get_db()
    conn.execute("DELETE FROM questions WHERE id = ?", (question_id,))
    conn.commit()
    conn.close()
    return {"message": "删除成功"}


@router.get("/admin/all")
def admin_list_all(
    page: int = 1,
    limit: int = 50,
    _admin: AdminSession = Depends(require_admin),
):
    """管理员查看所有问答（含已发布和待审核）"""
    conn = get_db()
    offset = (page - 1) * limit
    total = conn.execute("SELECT COUNT(*) FROM questions").fetchone()[0]
    rows = conn.execute(
        """SELECT q.*, a.content as answer_content, a.id as answer_id, a.status as answer_status
           FROM questions q
           LEFT JOIN answers a ON a.question_id = q.id
           ORDER BY q.created_at DESC LIMIT ? OFFSET ?""",
        (limit, offset),
    ).fetchall()
    conn.close()

    return {
        "questions": [
            {
                "id": row["id"],
                "author": row["author"],
                "content": row["content"],
                "created_at": row["created_at"],
                "answer": {
                    "id": row["answer_id"],
                    "content": row["answer_content"],
                    "status": row["answer_status"],
                } if row["answer_id"] else None,
            }
            for row in rows
        ],
        "total": total,
        "page": page,
    }


@router.post("/answers/{answer_id}/like")
def like_answer(answer_id: int):
    """给回答点赞"""
    conn = get_db()
    answer = conn.execute("SELECT id, likes FROM answers WHERE id = ?", (answer_id,)).fetchone()
    if not answer:
        conn.close()
        raise HTTPException(status_code=404, detail="回答不存在")
    conn.execute("UPDATE answers SET likes = likes + 1 WHERE id = ?", (answer_id,))
    conn.commit()
    new_likes = conn.execute("SELECT likes FROM answers WHERE id = ?", (answer_id,)).fetchone()["likes"]
    conn.close()
    return {"likes": new_likes}


@router.get("/stats")
def get_stats():
    """获取首页数据统计"""
    conn = get_db()
    published_qa = conn.execute(
        "SELECT COUNT(*) FROM answers WHERE status = 'published'"
    ).fetchone()[0]
    total_courseware = conn.execute("SELECT COUNT(*) FROM courseware").fetchone()[0]
    total_messages = conn.execute("SELECT COUNT(*) FROM messages").fetchone()[0]
    total_likes = conn.execute("SELECT COALESCE(SUM(likes), 0) FROM answers WHERE status = 'published'").fetchone()[0]
    conn.close()
    return {
        "published_qa": published_qa,
        "total_courseware": total_courseware,
        "total_messages": total_messages,
        "total_likes": total_likes,
    }


class AnalyzeRequest(BaseModel):
    prompt: str


@router.post("/analyze-personality")
async def analyze_personality(req: AnalyzeRequest):
    """调用 DeepSeek 分析性格测试结果"""
    result = await ask_deepseek(req.prompt)
    return {"result": result}


# === 追问功能 ===

@router.get("/questions/{question_id}/follow-ups")
def list_follow_ups(question_id: int):
    """获取某问题的所有追问（仅已发布的）"""
    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM follow_ups WHERE question_id = ? AND status = 'published' ORDER BY created_at ASC",
        (question_id,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


@router.post("/questions/{question_id}/follow-ups")
async def create_follow_up(question_id: int, req: FollowUpCreate):
    """学生发起追问，AI 自动回答"""
    if not req.content.strip():
        raise HTTPException(status_code=400, detail="内容不能为空")

    conn = get_db()
    # 检查问题存在
    q = conn.execute("SELECT * FROM questions WHERE id = ?", (question_id,)).fetchone()
    if not q:
        conn.close()
        raise HTTPException(status_code=404, detail="问题不存在")

    # 获取原始问答作为上下文
    answer = conn.execute(
        "SELECT content FROM answers WHERE question_id = ? AND status = 'published'",
        (question_id,),
    ).fetchone()

    prev_follow_ups = conn.execute(
        "SELECT content, answer_content FROM follow_ups WHERE question_id = ? AND status = 'published' ORDER BY created_at ASC",
        (question_id,),
    ).fetchall()

    # 构建 AI 追问上下文
    context = f"""【学生原始问题】{q['content']}
【AI 原始回答】{answer['content'] if answer else '暂无'}"""
    if prev_follow_ups:
        context += "\n\n【之前的追问对话】\n"
        for i, fu in enumerate(prev_follow_ups):
            context += f"追问{i+1}：{fu['content']}\n回答{i+1}：{fu['answer_content']}\n"

    ai_prompt = f"""以下是一个高中生在专业问答区的追问。你需要结合之前的对话上下文来回答。

{context}

【学生新的追问】{req.content}

请以"躬行启杭智能大模型"的身份，用亲切的学长/学姐口吻回答。注意：
1. 这次追问是建立在前面对话基础上的，不要重复之前已经说过的内容
2. 回答要完整，因为学生可能无法再次追问
3. 如果追问太模糊，尝试猜测真实意图
4. 用 Markdown 格式，但控制字数在300-600字内（追问不需要像原始回答那么长）"""

    ai_answer = await ask_deepseek(ai_prompt)

    cursor = conn.execute(
        "INSERT INTO follow_ups (question_id, author, content, answer_content, status) VALUES (?, ?, ?, ?, 'pending')",
        (question_id, req.author.strip() or "匿名", req.content.strip(), ai_answer),
    )
    conn.commit()
    new_id = cursor.lastrowid
    conn.close()

    return {"id": new_id, "message": "追问已提交，AI正在生成回答，审核通过后可见"}


@router.get("/follow-ups/pending")
def list_pending_follow_ups(
    _admin: AdminSession = Depends(require_admin),
):
    """管理员查看待审核的追问"""
    conn = get_db()
    rows = conn.execute(
        """SELECT f.*, q.content as question_content
           FROM follow_ups f
           JOIN questions q ON q.id = f.question_id
           WHERE f.status = 'pending'
           ORDER BY f.created_at DESC"""
    ).fetchall()
    conn.close()

    return [
        {
            "id": row["id"],
            "question_id": row["question_id"],
            "question_content": row["question_content"],
            "author": row["author"],
            "content": row["content"],
            "answer_content": row["answer_content"],
            "created_at": row["created_at"],
        }
        for row in rows
    ]


@router.put("/follow-ups/{follow_up_id}/review")
def review_follow_up(
    follow_up_id: int,
    review: FollowUpReview,
    _admin: AdminSession = Depends(require_admin_write),
):
    """管理员审核追问"""
    if review.status not in ("published", "rejected"):
        raise HTTPException(status_code=400, detail="状态无效")

    conn = get_db()
    conn.execute(
        "UPDATE follow_ups SET status = ? WHERE id = ?",
        (review.status, follow_up_id),
    )
    conn.commit()
    conn.close()
    return {"message": f"审核完成，状态：{review.status}"}


@router.delete("/follow-ups/{follow_up_id}")
def delete_follow_up(
    follow_up_id: int,
    _admin: AdminSession = Depends(require_admin_write),
):
    """管理员删除追问"""
    conn = get_db()
    conn.execute("DELETE FROM follow_ups WHERE id = ?", (follow_up_id,))
    conn.commit()
    conn.close()
    return {"message": "删除成功"}
