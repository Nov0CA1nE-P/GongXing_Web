from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict, Field
from abuse_protection import (
    AI_GLOBAL_RULES,
    consume_rules,
    public_identity,
    rule,
    visitor_and_ip_rules,
)
from auth import AdminSession, require_admin, require_admin_write
from config import UPLOADS_DIR
from database import get_db
from file_storage import public_pdf_filename
from services.ai_service import ask_deepseek

router = APIRouter(prefix="/api/qanda", tags=["qanda"])


class QuestionCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    author: str = Field(default="匿名", max_length=50)
    content: str = Field(min_length=1, max_length=2000)


class AnswerReview(BaseModel):
    status: str  # "published" 或 "rejected"
    content: str | None = None  # 管理员修改后的内容（可选）


class FollowUpCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    author: str = Field(default="匿名", max_length=50)
    content: str = Field(min_length=1, max_length=1000)


class FollowUpReview(BaseModel):
    status: str


@router.get("/questions")
def list_questions(
    page: int = Query(default=1, ge=1, le=10000),
    limit: int = Query(default=20, ge=1, le=100),
):
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
async def create_question(q: QuestionCreate, request: Request):
    """学生提交问题，自动触发AI回答"""
    if not q.content.strip():
        raise HTTPException(status_code=400, detail="问题内容不能为空")

    identity = public_identity(request)
    rules = visitor_and_ip_rules(
        identity,
        "qanda-question",
        visitor_limits=((2, 3600), (5, 86400)),
        ip_limits=((60, 3600), (150, 86400)),
    )
    consume_rules(rules + AI_GLOBAL_RULES)

    conn = get_db()

    # 插入问题
    cursor = conn.execute(
        "INSERT INTO questions (author, content) VALUES (?, ?)",
        (q.author.strip() or "匿名", q.content.strip()),
    )
    question_id = cursor.lastrowid
    conn.commit()
    conn.close()

    # 调用AI生成回答
    ai_answer = await ask_deepseek(q.content.strip())

    # 保存AI回答（状态为pending待审核）
    conn = get_db()
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
def like_answer(answer_id: int, request: Request):
    """给回答点赞"""
    conn = get_db()
    answer = conn.execute("SELECT id, likes FROM answers WHERE id = ?", (answer_id,)).fetchone()
    if not answer:
        conn.close()
        raise HTTPException(status_code=404, detail="回答不存在")
    conn.close()
    identity = public_identity(request)
    rules = visitor_and_ip_rules(
        identity,
        "qanda-like",
        visitor_limits=((10, 3600), (50, 86400)),
        ip_limits=((300, 3600), (1500, 86400)),
    )
    rules.append(
        rule(
            "qanda-like:target",
            f"{identity.visitor_id}:{answer_id}",
            1,
            86400,
        )
    )
    consume_rules(rules)
    conn = get_db()
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
    courseware_rows = conn.execute("SELECT * FROM courseware").fetchall()
    total_courseware = sum(
        1
        for row in courseware_rows
        if public_pdf_filename(row, uploads_dir=UPLOADS_DIR) is not None
    )
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
    model_config = ConfigDict(extra="forbid")

    class Scores(BaseModel):
        model_config = ConfigDict(extra="forbid")

        science: int = Field(ge=8, le=32)
        hands_on: int = Field(ge=8, le=32)
        programming: int = Field(ge=8, le=32)
        interpersonal: int = Field(ge=8, le=32)
        creativity: int = Field(ge=8, le=32)
        management: int = Field(ge=10, le=40)

    scores: Scores


PERSONALITY_DIMENSIONS = (
    ("science", "数理思维", 32),
    ("hands_on", "动手实践", 32),
    ("programming", "编程与逻辑", 32),
    ("interpersonal", "人际沟通", 32),
    ("creativity", "创意表达", 32),
    ("management", "商业与管理", 40),
)


def build_personality_prompt(scores: AnalyzeRequest.Scores) -> str:
    percentages = [
        (label, round(getattr(scores, key) / maximum * 100))
        for key, label, maximum in PERSONALITY_DIMENSIONS
    ]
    ranking = sorted(percentages, key=lambda item: item[1], reverse=True)
    score_text = "，".join(
        f"{label}：{percentage}%" for label, percentage in percentages
    )
    top_text = "\n".join(
        f"{index}. {label}（{percentage}%）"
        for index, (label, percentage) in enumerate(ranking[:3], start=1)
    )
    return f"""以下是一个高中生完成专业性格测试后的六维度结果。

【六维度得分】
{score_text}

【最突出的三个维度】
{top_text}

请以“躬行启杭智能大模型”的身份，用亲切的学长/学姐口吻生成分析：
1. 用2-3句话概括性格特点和学习风格。
2. 推荐3-5个专业方向，说明匹配原因、专业内容和未来方向。
3. 给出2-3条大学学习与发展建议。
4. 明确测试仅供参考，鼓励通过实践继续探索。

使用 Markdown，直接称呼“你”，不要声称看到了测试题之外的信息。"""


@router.post("/analyze-personality")
async def analyze_personality(req: AnalyzeRequest, request: Request):
    """调用 DeepSeek 分析性格测试结果"""
    identity = public_identity(request)
    rules = visitor_and_ip_rules(
        identity,
        "qanda-personality",
        visitor_limits=((3, 3600), (6, 86400)),
        ip_limits=((90, 3600), (180, 86400)),
    )
    consume_rules(rules + AI_GLOBAL_RULES)
    result = await ask_deepseek(build_personality_prompt(req.scores))
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
async def create_follow_up(
    question_id: int,
    req: FollowUpCreate,
    request: Request,
):
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
        """SELECT content, answer_content FROM follow_ups
           WHERE question_id = ? AND status = 'published'
           ORDER BY created_at DESC, id DESC LIMIT 5""",
        (question_id,),
    ).fetchall()
    conn.close()

    identity = public_identity(request)
    rules = visitor_and_ip_rules(
        identity,
        "qanda-follow-up",
        visitor_limits=((3, 3600), (8, 86400)),
        ip_limits=((90, 3600), (240, 86400)),
    )
    consume_rules(rules + AI_GLOBAL_RULES)

    # 只采用有上限的最近历史，并按时间正序呈现。
    context = f"""【学生原始问题】{q['content'][:1000]}
【AI 原始回答】{(answer['content'] if answer else '暂无')[:1500]}"""
    if prev_follow_ups:
        context += "\n\n【之前的追问对话】\n"
        for i, fu in enumerate(reversed(prev_follow_ups)):
            context += (
                f"追问{i+1}：{(fu['content'] or '')[:300]}\n"
                f"回答{i+1}：{(fu['answer_content'] or '')[:700]}\n"
            )

    ai_prompt = f"""以下是一个高中生在专业问答区的追问。你需要结合之前的对话上下文来回答。

{context}

【学生新的追问】{req.content}

请以"躬行启杭智能大模型"的身份，用亲切的学长/学姐口吻回答。注意：
1. 这次追问是建立在前面对话基础上的，不要重复之前已经说过的内容
2. 回答要完整，因为学生可能无法再次追问
3. 如果追问太模糊，尝试猜测真实意图
4. 用 Markdown 格式，但控制字数在300-600字内（追问不需要像原始回答那么长）"""

    ai_answer = await ask_deepseek(ai_prompt)

    conn = get_db()
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
