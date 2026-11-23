"""附件提示：带文件的消息给模型一条只读提示，引导用 dsh_task 读取。"""

from pathlib import Path
from typing import TYPE_CHECKING, Dict, List

from src.common.prompt_i18n import load_prompt

if TYPE_CHECKING:
    from src.chat.message_receive.message import SessionMessage

SUPPORTED_TEXT_SUFFIXES = (".txt", ".md", ".markdown", ".csv", ".json")


def collect_attachments(message: "SessionMessage") -> List[Dict[str, str]]:
    """列出当前消息里的文件附件，并给出本地缓存路径；图片不在此列。"""

    from src.common.data_models.message_component_data_model import FileComponent
    from src.files.service import get_file_service

    components = [
        component for component in message.raw_message.components
        if isinstance(component, FileComponent) and component.file_ref
    ]
    if not components:
        return []
    store = get_file_service().store
    items: List[Dict[str, str]] = []
    for component in components:
        try:
            path = str(store.path(component.file_ref))
        except Exception:
            path = ""
        items.append({"name": component.name or "未命名文件", "file_ref": component.file_ref, "path": path})
    return items


def attachment_mode(name: str) -> str:
    """按扩展名给出处理方式：直接读、先转 Markdown、还是交给 worker。"""

    suffix = Path(name).suffix.lower()
    if suffix in SUPPORTED_TEXT_SUFFIXES:
        return "可直接 files_read_text"
    if suffix == ".pdf":
        return "先用 files_convert 转 Markdown 再读"
    return "需 dsh_task 处理"


def build_attachment_hint(attachments: List[Dict[str, str]]) -> str:
    lines = []
    for item in attachments:
        mode = attachment_mode(item["name"])
        path = item["path"] or "未缓存，先调用 files_download"
        lines.append(f"- {item['name']}（file_ref: {item['file_ref']}，{mode}）本地路径：{path}")
    return load_prompt("dsh_worker_attachment_hint", files="\n".join(lines)).strip()
