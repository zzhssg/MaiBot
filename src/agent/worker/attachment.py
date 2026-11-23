"""附件提示：带文件的消息给模型一条只读提示，引导用 dsh_task 读取。"""

from typing import TYPE_CHECKING

from src.common.prompt_i18n import load_prompt

if TYPE_CHECKING:
    from src.chat.message_receive.message import SessionMessage


def has_file_attachment(message: "SessionMessage") -> bool:
    """只认文件组件；图片走原生视觉链路，不触发这条提示。"""

    from src.common.data_models.message_component_data_model import FileComponent

    return any(isinstance(component, FileComponent) for component in message.raw_message.components)


def build_attachment_hint() -> str:
    return load_prompt("dsh_worker_attachment_hint").strip()
