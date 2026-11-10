import io
import re
import pdfplumber
from loguru import logger
from pdf2image import convert_from_bytes
from docx import Document
from openpyxl import load_workbook
from pptx import Presentation
from PIL import Image
from services.llm import extract_text_from_image


def _page_to_jpeg_bytes(img) -> bytes:
    """
    Rasterized PDF pages are encoded to JPEG explicitly here — a deliberate,
    single-source-of-truth format decision, not whatever a library default
    happens to produce (that mismatch, vs. the hardcoded media_type Claude
    Vision was sent, was the root cause of prior "invalid_request_error:
    image was specified using image/png ... but appears to be image/jpeg"
    failures). Also force RGB: pdf2image can hand back RGBA (transparency)
    or CMYK pages depending on the source PDF, and PIL's JPEG encoder can't
    write those modes at all — that raised an unhandled/oddly-generic
    "cannot write mode X as JPEG" error, which is the likely cause of the
    plain "Could not process image" failures seen alongside the media-type
    ones.
    """
    if img.mode != "RGB":
        img = img.convert("RGB")
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    return buf.getvalue()


def _normalize_image_bytes(raw_bytes: bytes) -> bytes:
    """
    Embedded PPTX pictures come in whatever format/color-mode PowerPoint
    stored them in — sometimes CMYK JPEG, sometimes a non-standard encoding
    that Claude Vision rejects with a generic "Could not process image".
    Re-decoding and re-encoding through Pillow normalizes any input into a
    clean, standard RGB JPEG before it's ever sent, the same protection
    _page_to_jpeg_bytes already gives the PDF OCR path.
    """
    img = Image.open(io.BytesIO(raw_bytes))
    if img.mode != "RGB":
        img = img.convert("RGB")
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    return buf.getvalue()


def _looks_corrupted(text: str) -> bool:

    stripped = text.strip()
    if len(stripped) < 50:
        return True

    arabic_chars = len(re.findall(r'[\u0600-\u06FF]', stripped))
    total_chars = len(re.sub(r'\s', '', stripped))
    if total_chars == 0:
        return True

    arabic_ratio = arabic_chars / total_chars

    if arabic_ratio < 0.05 and total_chars < 300:
        return True

    return False


def extract_text_from_pdf(file_bytes: bytes) -> str:
    text_parts = []
    with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
        for page in pdf.pages:
            page_text = page.extract_text()
            if page_text and page_text.strip():
                text_parts.append(page_text)

    full_text = "\n".join(text_parts)

    if _looks_corrupted(full_text):
        print(f"⚠️ Extraction looks corrupted/too short (len={len(full_text.strip())}) — using OCR")
        text_parts = []
        try:
            images = convert_from_bytes(file_bytes, dpi=200, fmt="jpeg")
            for i, img in enumerate(images):
                img_bytes = _page_to_jpeg_bytes(img)
                ocr_text = extract_text_from_image(img_bytes)
                print(f"📄 Page {i+1} OCR: {ocr_text[:300]}")
                if ocr_text.strip():
                    text_parts.append(ocr_text)
        except Exception as e:
            logger.exception(f"PDF OCR fallback failed (whole-document mode): {e}")
            raise ValueError(f"OCR failed: {str(e)}")
    else:
        print(f"✅ Text extracted directly: {full_text[:300]}")

    if not text_parts:
        raise ValueError("Could not extract any text from this pdf")
    return "\n".join(text_parts)


def extract_text_from_docx(file_bytes: bytes) -> str:
    doc = Document(io.BytesIO(file_bytes))
    return "\n".join(p.text for p in doc.paragraphs if p.text.strip())


def extract_text_from_xlsx(file_bytes: bytes) -> str:
    wb = load_workbook(io.BytesIO(file_bytes), read_only=True, data_only=True)
    text_parts = []
    for sheet in wb.worksheets:
        for row in sheet.iter_rows(values_only=True):
            cells = [str(c) for c in row if c is not None]
            if cells:
                text_parts.append(" | ".join(cells))
    return "\n".join(text_parts)


def extract_text_from_txt(file_bytes: bytes) -> str:
    return file_bytes.decode("utf-8", errors="ignore")


def extract_text_from_pptx(file_bytes: bytes) -> str:
    import io
    try:
        prs = Presentation(io.BytesIO(file_bytes))
    except Exception:
        raise ValueError("Invalid or corrupted PowerPoint file")

    text_parts = []
    for slide in prs.slides:
        for shape in slide.shapes:
            if shape.has_text_frame:
                for paragraph in shape.text_frame.paragraphs:
                    line = "".join(run.text for run in paragraph.runs)
                    if line.strip():
                        text_parts.append(line)
            if shape.shape_type == 13:
                try:
                    # Raw embedded picture bytes, in whatever format/color-mode
                    # PowerPoint stored them (often JPEG, sometimes PNG, and
                    # sometimes CMYK or otherwise non-standard). Normalize
                    # through Pillow before OCR — same protection the PDF OCR
                    # path gets from _page_to_jpeg_bytes — since Claude Vision
                    # rejects some raw embedded encodings outright.
                    image_bytes = _normalize_image_bytes(shape.image.blob)
                    image_text = extract_text_from_image(image_bytes)
                    if image_text.strip():
                        text_parts.append(image_text)
                except Exception:
                    pass
    return "\n".join(text_parts)


def extract_text(filename: str, file_bytes: bytes) -> str:
    name = filename.lower()
    if name.endswith(".pdf"):
        text = extract_text_from_pdf(file_bytes)
    elif name.endswith(".docx"):
        text = extract_text_from_docx(file_bytes)
    elif name.endswith(".xlsx"):
        text = extract_text_from_xlsx(file_bytes)
    elif name.endswith(".txt"):
        text = extract_text_from_txt(file_bytes)
    elif name.endswith((".pptx", ".ppt")):
        text = extract_text_from_pptx(file_bytes)
    else:
        raise ValueError(f"Unsupported file type: {filename}")

    return text.replace("\x00", "")


def extract_slides_from_pptx(file_bytes: bytes) -> list[dict]:
    import io
    from pptx import Presentation
    from services.llm import extract_text_from_image

    try:
        prs = Presentation(io.BytesIO(file_bytes))
    except Exception:
        raise ValueError("invalid or corrupted powerpoint file")

    slides_out = []
    for slide_num, slide in enumerate(prs.slides, start=1):
        title = None
        text_parts = []

        for shape in slide.shapes:
            if shape.has_text_frame:
                for paragraph in shape.text_frame.paragraphs:
                    line = "".join(run.text for run in paragraph.runs)
                    if line.strip():
                        if title is None:
                            title = line.strip()
                        text_parts.append(line)
            if shape.shape_type == 13:
                try:
                    # Raw embedded picture bytes, in whatever format/color-mode
                    # PowerPoint stored them (often JPEG, sometimes PNG, and
                    # sometimes CMYK or otherwise non-standard). Normalize
                    # through Pillow before OCR — same protection the PDF OCR
                    # path gets from _page_to_jpeg_bytes — since Claude Vision
                    # rejects some raw embedded encodings outright.
                    image_bytes = _normalize_image_bytes(shape.image.blob)
                    image_text = extract_text_from_image(image_bytes)
                    if image_text.strip():
                        text_parts.append(image_text)
                except Exception:
                    pass

        full_text = "\n".join(text_parts).strip()
        if full_text:
            slides_out.append({
                "slide_number": slide_num,
                "title": title,
                "text": full_text,
            })

    if not slides_out:
        raise ValueError("Could not extract any text from this powerpoint file")

    return slides_out
