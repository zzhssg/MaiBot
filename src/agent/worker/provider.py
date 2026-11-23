"""DSH Worker 工具：把需要动电脑的活派给后台 dsh，结果回到当前聊天。"""

from typing import Any, Dict, List, Optional

import json

from src.agent.worker.policy import screen_allowed, worker_allowed
from src.agent.worker.pool import WorkerPool, worker_pool
from src.config.config import global_config
from src.core.tooling import ToolAvailabilityContext, ToolExecutionContext, ToolExecutionResult, ToolInvocation, ToolSpec


def tool_specs() -> List[ToolSpec]:
    """三个工具都直接可见：路由靠模型知道它存在，而不是先去 tool_search 找。"""

    definitions = [
        (
            "dsh_task",
            "把一个需要动电脑的任务派给本机 DSH 执行：读文件、改代码、跑命令、查日志、写插件、操作图形界面。"
            "调用立即返回 task_id，任务在后台运行；结束后结果会作为内部消息送回，你要用用户习惯的口吻转述，不要贴原文、不要复述过程。"
            "用户给出本机路径（日志、代码、文件、目录）让你查看时直接派单，不要说看不到本地目录。只派自包含、可验收的任务；常识、闲聊、记忆查询不要用它；简单的公开信息搜索用 web_search，不要派 worker。",
            {
                "brief": {"type": "string", "description": "写清目标、验收标准、不能做的事、涉及的路径；不要把整段聊天粘进来。"},
                "screen": {"type": "boolean", "description": "需要看屏幕或操作鼠标键盘时填 true；只有主人授权的私聊可用。", "default": False},
                "continue_from": {"type": "string", "description": "上一个任务返回的会话句柄；追问同一件事时传它，过期或不匹配会报错。"},
            },
            ["brief"],
        ),
        (
            "dsh_status",
            "查看后台 DSH 任务。task_id 留空时列出当前聊天的最近任务；任务仍在跑时会提示不要轮询。",
            {"task_id": {"type": "string", "description": "任务 id；留空查看最近任务。"}},
            [],
        ),
        (
            "dsh_stop",
            "终止仍在运行的后台 DSH 任务；已结束或不属于当前聊天的任务会被拒绝。",
            {"task_id": {"type": "string", "description": "要终止的任务 id。"}},
            ["task_id"],
        ),
    ]
    return [
        ToolSpec(
            name=name,
            description=description,
            provider_name="dsh_worker",
            provider_type="builtin",
            parameters_schema={
                "type": "object",
                "properties": properties,
                "required": required,
                "additionalProperties": False,
            },
            metadata={"visibility": "visible"},
        )
        for name, description, properties, required in definitions
    ]


class DshWorkerToolProvider:
    provider_name = "dsh_worker"
    provider_type = "builtin"

    def __init__(self, pool: WorkerPool = worker_pool) -> None:
        self.pool = pool

    async def list_tools(self, context: Optional[ToolAvailabilityContext] = None) -> List[ToolSpec]:
        if not global_config.agent.worker.enabled:
            return []
        if context is None or not self._allowed(context):
            return []
        return tool_specs()

    async def invoke(self, invocation: ToolInvocation, context: Optional[ToolExecutionContext] = None) -> ToolExecutionResult:
        try:
            if context is None:
                raise PermissionError("DSH Worker 工具需要可信执行上下文。")
            if not global_config.agent.worker.enabled:
                raise PermissionError("DSH Worker 未启用。")
            if not self._allowed(context):
                raise PermissionError("当前聊天没有派发 DSH 任务的权限。")
            arguments: Dict[str, Any] = invocation.arguments
            if invocation.tool_name == "dsh_task":
                payload = await self._submit(arguments, context)
            elif invocation.tool_name == "dsh_status":
                payload = self.pool.status(context.session_id, str(arguments.get("task_id", "")).strip())
            elif invocation.tool_name == "dsh_stop":
                payload = self._stop(arguments, context)
            else:
                raise ValueError(f"未知 DSH Worker 工具：{invocation.tool_name}")
            return ToolExecutionResult(
                tool_name=invocation.tool_name,
                success=True,
                content=json.dumps(payload, ensure_ascii=False),
                structured_content=payload,
            )
        except (OSError, RuntimeError, ValueError, KeyError) as exc:
            return ToolExecutionResult(
                tool_name=invocation.tool_name,
                success=False,
                error_message=f"{type(exc).__name__}: {exc}",
            )

    async def _submit(self, arguments: Dict[str, Any], context: ToolExecutionContext) -> Dict[str, Any]:
        brief = str(arguments.get("brief", "")).strip()
        if not brief:
            raise ValueError("brief 不能为空：写清楚要做什么以及怎样算完成。")
        screen = bool(arguments.get("screen", False))
        if screen and not self._screen_allowed(context):
            raise PermissionError("当前聊天不允许使用屏幕操作。")
        continue_from = str(arguments.get("continue_from", "")).strip()
        task = self.pool.submit(
            chat_id=context.session_id, brief=brief, screen=screen, continue_from=continue_from,
        )
        # 长任务必须先给用户一个反馈：这里直接发一句确认，不依赖 Planner 记得。
        ack_sent = await self._send_ack(context.session_id)
        return {
            "task_id": task.task_id, "status": task.status, "backend": task.backend, "session": task.session,
            "notice": "已先回用户一句确认，不要重复确认；结果回来后再交代。" if ack_sent else
                      "请立刻 reply 一句确认，再 wait 等结果。",
        }

    @staticmethod
    async def _send_ack(session_id: str) -> bool:
        """派单后的固定反馈，失败只记日志，不影响任务本身。"""

        from src.services.send_service import text_to_stream

        try:
            return bool(await text_to_stream("去看下，等会儿说。", session_id, storage_message=False))
        except Exception:
            from src.common.logger import get_logger

            get_logger("agent.worker.provider").exception(f"派单确认发送失败: session_id={session_id}")
            return False

    def _stop(self, arguments: Dict[str, Any], context: ToolExecutionContext) -> Dict[str, Any]:
        task_id = str(arguments.get("task_id", "")).strip()
        if not task_id:
            raise ValueError("task_id 不能为空。")
        if not self.pool.stop(context.session_id, task_id):
            raise ValueError(f"任务不存在、已结束或不属于当前聊天：{task_id}")
        return {"task_id": task_id, "status": "cancelled"}

    def _allowed(self, context: Optional[ToolAvailabilityContext | ToolExecutionContext]) -> bool:
        if context is None:
            return False
        return worker_allowed(
            session_id=context.session_id,
            platform=context.platform,
            user_id=context.user_id,
            group_id=context.group_id,
            is_group=bool(context.is_group_chat),
        )

    def _screen_allowed(self, context: ToolExecutionContext) -> bool:
        return screen_allowed(platform=context.platform, user_id=context.user_id)

    async def close(self) -> None:
        """Provider 按聊天运行时创建，会话池是进程级资源，由 runtime.graceful_shutdown 统一关闭。"""
