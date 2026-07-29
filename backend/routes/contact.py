from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field
from abuse_protection import (
    consume_rules,
    public_identity,
    visitor_and_ip_rules,
)
from auth import AdminSession, require_admin
from database import get_db

router = APIRouter(prefix="/api/contact", tags=["contact"])


class ContactSubmit(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=100)
    contact_info: str = Field(default="", max_length=200)
    message: str = Field(min_length=1, max_length=2000)


@router.post("/submit")
def submit_contact(data: ContactSubmit, request: Request):
    """学生提交联系表单"""
    if not data.name.strip() or not data.message.strip():
        raise HTTPException(status_code=400, detail="姓名和留言内容不能为空")

    identity = public_identity(request)
    consume_rules(
        visitor_and_ip_rules(
            identity,
            "contact",
            visitor_limits=((3, 3600), (10, 86400)),
            ip_limits=((60, 3600), (200, 86400)),
        )
    )

    conn = get_db()
    conn.execute(
        "INSERT INTO contact_submissions (name, contact_info, message) VALUES (?, ?, ?)",
        (data.name.strip(), data.contact_info.strip(), data.message.strip()),
    )
    conn.commit()
    conn.close()
    return {"message": "提交成功，我们会尽快联系你！"}


@router.get("/submissions")
def list_submissions(
    _admin: AdminSession = Depends(require_admin),
):
    """管理员查看联系表单提交记录"""
    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM contact_submissions ORDER BY created_at DESC"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]
