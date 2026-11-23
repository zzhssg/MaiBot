"""文档文本提取：把 PDF 转成带页码的 Markdown，供 files_convert 使用。"""

from dataclasses import dataclass
from io import BytesIO

import unicodedata

from pypdf import PdfReader

# 单次转换的页数上限，防止超大 PDF 把一次工具调用拖死。
MAX_PAGES = 500
# 少于这个字符数就当作没有文本层（扫描件），交给 worker 走视觉或 OCR。
MIN_TEXT_CHARS = 10


@dataclass(slots=True)
class ExtractedDocument:
    """一次 PDF 提取的结果；页数与异常页都保留，方便调用方判断完整性。"""

    text: str
    pages: int
    empty_pages: int
    failed_pages: int
    truncated: bool


def extract_pdf_text(data: bytes, *, max_pages: int = MAX_PAGES) -> ExtractedDocument:
    """提取 PDF 文本层；没有文本层时抛错，不返回空文档冒充成功。"""

    reader = PdfReader(BytesIO(data))
    total_pages = len(reader.pages)
    pages = min(total_pages, max_pages)
    sections: list[str] = []
    empty_pages = 0
    failed_pages = 0
    for index in range(pages):
        try:
            raw = reader.pages[index].extract_text() or ""
        except Exception:
            failed_pages += 1
            raw = ""
        text = unicodedata.normalize("NFKC", raw).strip()
        if not text:
            empty_pages += 1
            continue
        sections.append(f"## 第 {index + 1} 页\n\n{text}")
    body = "\n\n".join(sections).strip()
    if len(body) < MIN_TEXT_CHARS:
        raise ValueError(
            "PDF 没有可提取的文本层（可能是扫描件或纯图片）；请用 dsh_task 渲染页面后走视觉识别或 OCR",
        )
    return ExtractedDocument(
        text=body,
        pages=pages,
        empty_pages=empty_pages,
        failed_pages=failed_pages,
        truncated=total_pages > pages,
    )
