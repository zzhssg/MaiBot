"""把 worker 结果包装成内部任务送回原聊天，由麦麦用自己的口吻转述。"""

from typing import Any, Dict

from src.agent.worker.tasks import DshTask
from src.common.prompt_i18n import load_prompt
from src.config.config import global_config

# 单条结果回送的上限；完整正文留在 DSH 会话里，避免把长报告灌进聊天上下文。
MAX_RESULT_CHARS = 8000


def build_delivery_text(task: DshTask) -> str:
    """按任务终态生成回送文本，措辞由 prompts/.../agent/dsh_worker_result.prompt 提供。"""

    preview = " ".join(task.brief.split())
    if len(preview) > 200:
        preview = preview[:200] + "…"
    result = task.result.strip()
    if len(result) > MAX_RESULT_CHARS:
        result = result[:MAX_RESULT_CHARS] + "\n…（结果过长，完整内容保留在 DSH 会话中）"
    if not result:
        result = f"没有正文输出。失败原因：{task.error}" if task.error else "没有正文输出。"
    ttl_minutes = max(1, int(global_config.agent.worker.session_ttl_seconds // 60))
    return load_prompt(
        "dsh_worker_result",
        task_id=task.task_id,
        status=task.status,
        backend=task.backend,
        session=task.session,
        ttl_minutes=ttl_minutes,
        duration=f"{task.elapsed_seconds:.1f}",
        brief=preview,
        result=result,
    ).strip()


def build_progress_text(task: DshTask) -> str:
    """长任务的进度心跳：只给一句现状，由麦麦决定要不要开口。"""

    total = max(0, int(task.elapsed_seconds))
    elapsed = f"{total} 秒" if total < 60 else f"{total // 60} 分 {total % 60} 秒"
    return load_prompt(
        "dsh_worker_progress",
        task_id=task.task_id,
        elapsed=elapsed,
        progress=task.progress or "刚接手",
    ).strip()


def build_interrupted_text(record: Dict[str, Any]) -> str:
    """进程重启后补发的中断说明，措辞同样走提示词模板。"""

    brief = " ".join(str(record.get("brief", "")).split())
    if len(brief) > 200:
        brief = brief[:200] + "…"
    return load_prompt(
        "dsh_worker_interrupted",
        task_id=str(record.get("task_id", "")),
        brief=brief,
    ).strip()


async def deliver_task_progress(task: DshTask) -> None:
    """把进度作为内部任务送回原聊天；Planner 自行决定说一句还是保持安静。"""

    from src.chat.heart_flow.heartflow_manager import heartflow_manager

    runtime = await heartflow_manager.get_or_create_heartflow_chat(task.chat_id)
    runtime.enqueue_internal_task(
        source_kind="dsh_worker_progress",
        text=build_progress_text(task),
        reason="DSH 后台任务进度",
    )


async def deliver_task_result(task: DshTask) -> None:
    """追加到原聊天历史末尾并唤醒 Planner；不回填到当初调用工具的位置。"""

    from src.chat.heart_flow.heartflow_manager import heartflow_manager

    runtime = await heartflow_manager.get_or_create_heartflow_chat(task.chat_id)
    runtime.enqueue_internal_task(
        source_kind="dsh_worker_result",
        text=build_delivery_text(task),
        reason="DSH 后台任务结束",
    )
