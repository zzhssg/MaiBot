"""Worker 权限判定：工具暴露与 `/work` 指令共用同一套白名单。"""

from src.config.config import global_config
from src.core.local_operator import build_scoped_user_id, normalize_operator_permissions
from src.desktop_pet.chat_tools import is_owner_chat


def worker_allowed(*, session_id: str, platform: str, user_id: str, group_id: str = "", is_group: bool = False) -> bool:
    """主人私聊始终可用；其他聊天只能靠各自的白名单进入。"""

    worker = global_config.agent.worker
    if not worker.enabled:
        return False
    if is_owner_chat(session_id):
        return True
    if is_group or group_id:
        target = build_scoped_user_id(platform, group_id)
        return bool(target) and target in normalize_operator_permissions(worker.allow_groups)
    target = build_scoped_user_id(platform, user_id)
    return bool(target) and target in normalize_operator_permissions(worker.allow_users)


def screen_allowed(*, platform: str, user_id: str) -> bool:
    """屏幕操作只认显式名单，主人身份不自动放行。"""

    target = build_scoped_user_id(platform, user_id)
    return bool(target) and target in normalize_operator_permissions(global_config.agent.worker.screen_allow_users)
