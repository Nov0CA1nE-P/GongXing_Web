"""
PPT 转 PDF 工具脚本
使用 LibreOffice 或 python-pptx + pdfkit 将 PPT/PPTX 转换为 PDF 以便前端预览

用法：python convert_pptx.py <pptx文件路径>

依赖（可选，按需安装）：
  pip install python-pptx pdfkit
  或安装 LibreOffice 并确保在 PATH 中
"""
import sys
import os
import subprocess
import shutil

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
UPLOADS_DIR = os.path.join(DATA_DIR, "uploads")


def convert_with_libreoffice(input_path: str) -> str | None:
    """使用 LibreOffice 转换（推荐，效果好）"""
    try:
        subprocess.run(
            ["libreoffice", "--headless", "--convert-to", "pdf",
             "--outdir", UPLOADS_DIR, input_path],
            check=True, timeout=60,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        base = os.path.splitext(os.path.basename(input_path))[0]
        pdf_path = os.path.join(UPLOADS_DIR, f"{base}.pdf")
        if os.path.exists(pdf_path):
            return pdf_path
    except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
        pass
    return None


def main():
    if len(sys.argv) < 2:
        print("用法：python convert_pptx.py <pptx文件路径> [pptx文件路径2 ...]")
        print("")
        print("将 PPT/PPTX 文件转换为 PDF，放入 data/uploads/ 目录")
        print("需要安装 LibreOffice（推荐）")
        sys.exit(1)

    os.makedirs(UPLOADS_DIR, exist_ok=True)

    for filepath in sys.argv[1:]:
        if not os.path.exists(filepath):
            print(f"  [跳过] 文件不存在：{filepath}")
            continue

        if not filepath.lower().endswith(('.ppt', '.pptx')):
            print(f"  [跳过] 非PPT文件：{filepath}")
            continue

        print(f"转换中：{os.path.basename(filepath)}...")
        result = convert_with_libreoffice(filepath)
        if result:
            print(f"  ✅ 成功：{result}")
        else:
            print(f"  ❌ 失败：请安装 LibreOffice 或手动转换")


if __name__ == "__main__":
    main()
