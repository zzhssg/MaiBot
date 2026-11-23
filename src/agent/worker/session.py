"""一个聊天对应的 DSH 会话：纯文本 ACP，不挂任何会说话的麦麦工具。"""

from pathlib import Path
from typing import Any, Dict, List, Optional

import asyncio

from src.agent.acp import ACPConnection
from src.agent.config import AgentConfig
from src.common.logger import get_logger

logger = get_logger("agent.worker.session")


class WorkerTurnError(RuntimeError):
    """DSH 结束了一轮但没正常收尾；已收到的正文仍然要交给麦麦。"""

    def __init__(self, message: str, text: str = "") -> None:
        super().__init__(message)
        self.text = text


class WorkerTimeout(TimeoutError):
    """任务超时；已收到的正文保留，会话由池丢弃重建。"""

    def __init__(self, message: str, text: str = "") -> None:
        super().__init__(message)
        self.text = text


class WorkerSession:
    """持有一个 ACP 连接和一个 DSH 会话，只收集正文并返回给麦麦。"""

    def __init__(self, chat_id: str, config: AgentConfig, cwd: Path) -> None:
        self.chat_id = chat_id
        self.config = config
        self.cwd = cwd
        self.connection: Optional[ACPConnection] = None
        self.session_id = ""
        self._chunks: List[str] = []
        self._lock = asyncio.Lock()

    @property
    def alive(self) -> bool:
        """连接仍然可用；保留中的会话在追问时先做这个检查。"""

        return self.connection is not None and self.connection.failure is None

    async def start(self) -> None:
        """握手并新建会话，不挂 MCP：后台不需要、也不允许直接对 IM 说话。"""

        connection = ACPConnection(self._collect)
        try:
            await connection.initialize(self.config, self.cwd, "maibot-worker", mcp_port=None)
            session = await connection.open_session(str(self.cwd), None, None, self.config.acp_timeout)
            self.session_id = session["sessionId"]
            await connection.select_model(self.config, session, self.session_id)
        except BaseException:
            await connection.close(self.config.acp_timeout)
            raise
        self.connection = connection

    async def run(self, prompt: str, timeout: float) -> str:
        """发一轮 prompt 并返回收集到的正文；超时会取消会话，不做重放。"""

        if self.connection is None:
            raise RuntimeError("DSH 会话尚未建立")
        async with self._lock:
            self._chunks.clear()
            task = asyncio.create_task(self.connection.request("session/prompt", {
                "sessionId": self.session_id,
                "prompt": [{"type": "text", "text": prompt}],
            }), name="agent.worker.prompt")
            try:
                result = await asyncio.wait_for(asyncio.shield(task), timeout)
            except asyncio.TimeoutError:
                await self._cancel(task)
                raise WorkerTimeout(
                    f"DSH 任务超过 {timeout:.0f} 秒未完成，会话已取消", "".join(self._chunks).strip(),
                ) from None
            finally:
                if not task.done():
                    task.cancel()
                await asyncio.gather(task, return_exceptions=True)
            if result["stopReason"] != "end_turn":
                raise WorkerTurnError(
                    f"DSH 未正常结束（{result['stopReason']}），已收到的输出保留", "".join(self._chunks).strip(),
                )
            return "".join(self._chunks).strip()

    async def _cancel(self, task: asyncio.Task[Any]) -> None:
        """请求对端取消本轮；对端不确认就关闭连接，避免把未知状态留在会话里。"""

        if self.connection is None:
            return
        await self.connection.notify("session/cancel", {"sessionId": self.session_id})
        try:
            await asyncio.wait_for(asyncio.shield(task), min(self.config.acp_timeout, 2))
        except asyncio.TimeoutError:
            await self.close()

    async def _collect(self, params: Dict[str, Any]) -> None:
        """只收正文分片；思考过程、工具事件都不进入麦麦上下文。"""

        if params.get("sessionId") != self.session_id:
            return
        update = params.get("update", {})
        if update.get("sessionUpdate") != "agent_message_chunk":
            return
        content = update.get("content", {})
        if content.get("type") == "text" and content.get("text"):
            self._chunks.append(content["text"])

    async def close(self) -> None:
        """关闭连接；可重复调用。"""

        connection, self.connection = self.connection, None
        if connection is not None:
            await connection.close(min(self.config.acp_timeout, 5))
