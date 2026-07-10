import io
import re


def extract_text_from_pdf(file_bytes):
    try:
        import pdfplumber
        with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
            pages = [page.extract_text() or "" for page in pdf.pages]
        return "\n".join(pages).strip()
    except Exception as e:
        return f"[PDF extraction error: {e}]"


def extract_text_from_docx(file_bytes):
    try:
        from docx import Document
        doc = Document(io.BytesIO(file_bytes))
        paragraphs = [p.text for p in doc.paragraphs]
        return "\n".join(paragraphs).strip()
    except Exception as e:
        return f"[DOCX extraction error: {e}]"


def extract_text(file_name, file_bytes):
    name_lower = file_name.lower()
    if name_lower.endswith(".pdf"):
        return extract_text_from_pdf(file_bytes)
    elif name_lower.endswith(".docx") or name_lower.endswith(".doc"):
        return extract_text_from_docx(file_bytes)
    elif name_lower.endswith(".txt"):
        return file_bytes.decode("utf-8", errors="ignore")
    else:
        return ""


def guess_name_from_text(cv_text, sender_name):
    """Try to pull the candidate's name from the top of the CV text."""
    if sender_name and sender_name.strip():
        return sender_name.strip()
    lines = [l.strip() for l in cv_text.splitlines() if l.strip()]
    if lines:
        first = lines[0]
        # Likely a name if it's short and has no digits
        if len(first) < 50 and not re.search(r"\d", first):
            return first
    return "Unknown"
