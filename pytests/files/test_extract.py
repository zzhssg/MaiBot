from io import BytesIO

import pytest

from src.files.extract import extract_pdf_text


def build_pdf(lines):
    """构造一个只含标准 Helvetica 文本的最小 PDF，避免把二进制夹具放进仓库。"""

    content = "BT /F1 16 Tf 72 720 Td " + " ".join(f"({line}) Tj 0 -24 Td" for line in lines) + " ET"
    objects = [
        "<< /Type /Catalog /Pages 2 0 R >>",
        "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        "/Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>",
        f"<< /Length {len(content)} >>\nstream\n{content}\nendstream",
        "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out = BytesIO()
    out.write(b"%PDF-1.4\n")
    offsets = []
    for index, body in enumerate(objects, start=1):
        offsets.append(out.tell())
        out.write(f"{index} 0 obj\n{body}\nendobj\n".encode())
    xref = out.tell()
    out.write(f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode())
    for offset in offsets:
        out.write(f"{offset:010d} 00000 n \n".encode())
    out.write(
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    )
    return out.getvalue()


def test_extracts_text_with_page_markers():
    document = extract_pdf_text(build_pdf(["MaiBot PDF test", "Secret is BLUE-731"]))

    assert "BLUE-731" in document.text
    assert "## 第 1 页" in document.text
    assert document.pages == 1
    assert document.empty_pages == 0


def test_pdf_without_text_layer_is_rejected():
    with pytest.raises(ValueError, match="没有可提取的文本层"):
        extract_pdf_text(build_pdf([]))
