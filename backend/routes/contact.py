from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from auth import AdminSession, require_admin
from database import get_db

router = APIRouter(prefix="/api/contact", tags=["contact"])


class ContactSubmit(BaseModel):
    name: str
    contact_info: str = ""
    message: str


@router.post("/submit")
def submit_contact(data: ContactSubmit):
    """学生提交联系表单"""
    if not data.name.strip() or not data.message.strip():
        raise HTTPException(status_code=400, detail="姓名和留言内容不能为空")

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
