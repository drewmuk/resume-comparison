from pathlib import Path

import pdfplumber
from docx import Document


def parse_resume(file_path: Path) -> str:
    suffix = file_path.suffix.lower()
    if suffix == ".pdf":
        return _parse_pdf(file_path)
    elif suffix in (".docx", ".doc"):
        return _parse_docx(file_path)
    else:
        raise ValueError(
            f"Unsupported file format '{suffix}'. Please provide a .pdf or .docx file."
        )


def _parse_pdf(file_path: Path) -> str:
    pages = []
    with pdfplumber.open(file_path) as pdf:
        for page in pdf.pages:
            text = page.extract_text()
            if text:
                pages.append(text.strip())
    if not pages:
        raise ValueError("Could not extract text from the PDF. It may be image-based.")
    return "\n\n".join(pages)


def _parse_docx(file_path: Path) -> str:
    doc = Document(file_path)
    paragraphs = [p.text.strip() for p in doc.paragraphs if p.text.strip()]
    if not paragraphs:
        raise ValueError("Could not extract text from the DOCX file.")
    return "\n".join(paragraphs)
