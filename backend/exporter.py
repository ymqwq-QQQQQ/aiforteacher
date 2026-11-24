import io
import re
from datetime import datetime
from typing import Literal

from docx import Document
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer


def strip_thinking(text: str) -> str:
    return re.sub(r"<thinking>.*?</thinking>", "", text or "", flags=re.DOTALL).strip()


def format_filename(title: str, naming_pattern: str, ext: str) -> str:
    clean_title = re.sub(r"[^a-zA-Z0-9\u4e00-\u9fff_-]+", "_", (title or "lesson_plan")).strip("_") or "lesson_plan"
    date_str = datetime.now().strftime("%Y-%m-%d")
    base = (naming_pattern or "{title}_{date}").replace("{title}", clean_title).replace("{date}", date_str)
    base = re.sub(r"[^a-zA-Z0-9\u4e00-\u9fff_-]+", "_", base).strip("_") or clean_title
    return f"{base}.{ext}"


def export_content(content: str, fmt: Literal["md", "docx", "pdf"], title: str = "Lesson Plan") -> bytes:
    body = strip_thinking(content)
    if fmt == "md":
        md_text = f"# {title}\n\n{body}\n"
        return md_text.encode("utf-8")

    if fmt == "docx":
        doc = Document()
        doc.add_heading(title, level=1)
        for line in body.splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            if stripped.startswith("### "):
                doc.add_heading(stripped[4:], level=3)
            elif stripped.startswith("## "):
                doc.add_heading(stripped[3:], level=2)
            elif stripped.startswith("# "):
                doc.add_heading(stripped[2:], level=1)
            elif stripped.startswith("- ") or stripped.startswith("* "):
                doc.add_paragraph(stripped[2:], style="List Bullet")
            else:
                doc.add_paragraph(stripped)
        buf = io.BytesIO()
        doc.save(buf)
        return buf.getvalue()

    if fmt == "pdf":
        buf = io.BytesIO()
        pdf = SimpleDocTemplate(buf, pagesize=letter, title=title)
        styles = getSampleStyleSheet()
        body_style = ParagraphStyle("Body", parent=styles["Normal"], fontSize=10.5, leading=15, spaceAfter=6)
        heading_style = ParagraphStyle("Head", parent=styles["Heading2"], spaceBefore=10, spaceAfter=4)
        story = [Paragraph(title.replace("&", "&amp;").replace("<", "&lt;"), styles["Title"]), Spacer(1, 10)]
        for line in body.splitlines():
            stripped = line.strip()
            if not stripped:
                story.append(Spacer(1, 4))
                continue
            safe = stripped.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            if stripped.startswith("#"):
                clean_h = safe.lstrip("# ").strip()
                story.append(Paragraph(clean_h, heading_style))
            else:
                story.append(Paragraph(safe, body_style))
        pdf.build(story)
        return buf.getvalue()

    raise ValueError(f"Unsupported format: {fmt}")
