"""`/work` 显式派单指令：让用户绕过模型判断，直接要求后台执行。"""

from typing import Optional

from src.common.prompt_i18n import load_prompt

WORK_COMMAND = "/work"


def parse_work_command(text: Optional[str]) -> Optional[str]:
    """返回 `/work` 后面的内容；不是该指令时返回 None，空内容返回空串。"""

    if not text:
        return None
    stripped = text.strip()
    if stripped == WORK_COMMAND:
        return ""
    if stripped.startswith(f"{WORK_COMMAND} "):
        return stripped[len(WORK_COMMAND):].strip()
    return None


def build_work_task_text(content: str) -> str:
    """交给 Planner 的内部任务文本，要求它必须调用 dsh_task。"""

    return load_prompt("dsh_work_command", content=content).strip()
