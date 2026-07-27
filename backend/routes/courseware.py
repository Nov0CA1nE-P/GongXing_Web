import os
import shutil
from fastapi import APIRouter, UploadFile, File, HTTPException, Form
from database import get_db
from config import COURSEWARE_DIR, UPLOADS_DIR

router = APIRouter(prefix="/api/courseware", tags=["courseware"])

# 确保目录存在
os.makedirs(COURSEWARE_DIR, exist_ok=True)
os.makedirs(UPLOADS_DIR, exist_ok=True)


@router.get("/list")
def list_courseware(tag: str = ""):
    """获取所有课件列表，按日期倒序。可选按 tag 筛选"""
    conn = get_db()
    if tag:
        rows = conn.execute(
            "SELECT * FROM courseware WHERE tags LIKE ? ORDER BY date DESC",
            (f"%{tag}%",),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM courseware ORDER BY date DESC"
        ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


@router.get("/{courseware_id}")
def get_courseware(courseware_id: int):
    """获取单个课件详情"""
    conn = get_db()
    row = conn.execute(
        "SELECT * FROM courseware WHERE id = ?", (courseware_id,)
    ).fetchone()
    conn.close()
    if not row:
        raise HTTPException(status_code=404, detail="课件不存在")
    return dict(row)


@router.post("/upload")
def upload_courseware(
    title: str = Form(...),
    date: str = Form(...),
    description: str = Form(""),
    tags: str = Form(""),
    file: UploadFile = File(...),
):
    """上传新课件（管理员功能）"""
    if not file.filename.endswith(('.ppt', '.pptx', '.pdf')):
        raise HTTPException(status_code=400, detail="仅支持 PPT、PPTX、PDF 格式")

    # 保存原始文件
    ext = os.path.splitext(file.filename)[1]
    safe_name = f"{date}_{title}{ext}"
    file_path = os.path.join(UPLOADS_DIR, safe_name)

    with open(file_path, "wb") as f:
        shutil.copyfileobj(file.file, f)

    # 如果是 PPT/PPTX，暂时直接用原文件路径（PDF转换在后面手动或用脚本）
    pdf_path = ""
    pptx_path = ""
    if ext in ('.ppt', '.pptx'):
        pptx_path = file_path
    elif ext == '.pdf':
        pdf_path = file_path

    conn = get_db()
    cursor = conn.execute(
        "INSERT INTO courseware (title, date, description, tags, pdf_path, pptx_path) VALUES (?, ?, ?, ?, ?, ?)",
        (title, date, description, tags, pdf_path, pptx_path),
    )
    conn.commit()
    new_id = cursor.lastrowid
    conn.close()

    return {"id": new_id, "message": "上传成功"}


@router.delete("/{courseware_id}")
def delete_courseware(courseware_id: int):
    """删除课件"""
    conn = get_db()
    row = conn.execute("SELECT * FROM courseware WHERE id = ?", (courseware_id,)).fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="课件不存在")

    # 删除文件
    for path in [row["pdf_path"], row["pptx_path"]]:
        if path and os.path.exists(path):
            os.remove(path)

    conn.execute("DELETE FROM courseware WHERE id = ?", (courseware_id,))
    conn.commit()
    conn.close()
    return {"message": "删除成功"}
