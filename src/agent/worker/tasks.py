"""DSH Worker 的任务登记与状态机。"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Literal, Optional

import asyncio
import time

DshTaskStatus = Literal["running", "done", "failed", "timeout", "cancelled"]
DshTaskBackend = Literal["cli", "desktop"]

# 已结束任务的保留条数，供 dsh_status 回看；只保留最近结束的，运行中的不受限制。
DSH_FINISHED_TASK_KEEP_COUNT = 20


@dataclass(slots=True)
class DshTask:
    """一次派给 DSH 的后台任务。"""

    task_id: str
    chat_id: str
    brief: str
    backend: DshTaskBackend
    session: str = ""
    status: DshTaskStatus = "running"
    started_at: float = field(default_factory=time.time)
    finished_at: Optional[float] = None
    result: str = ""
    error: str = ""
    asyncio_task: Optional[asyncio.Task[None]] = None

    @property
    def elapsed_seconds(self) -> float:
        """任务已经运行（或总共运行）的秒数。"""

        return (self.finished_at or time.time()) - self.started_at

    def summary(self) -> Dict[str, Any]:
        """给 Planner 看的任务摘要，正文只留预览。"""

        return {
            "task_id": self.task_id,
            "status": self.status,
            "backend": self.backend,
            "session": self.session,
            "brief": self.brief[:200],
            "elapsed_seconds": round(self.elapsed_seconds, 1),
            "error": self.error,
            "result_preview": self.result[:300],
        }


class DshTaskRegistry:
    """进程内任务登记。不持久化：重启后旧任务不恢复，也不会重放外部副作用。"""

    def __init__(self) -> None:
        self._tasks: Dict[str, DshTask] = {}
        self._counter = 0

    @property
    def running_count(self) -> int:
        """当前仍在运行的任务数量。"""

        return sum(1 for task in self._tasks.values() if task.status == "running")

    def create(self, *, chat_id: str, brief: str, backend: DshTaskBackend, session: str) -> DshTask:
        """登记一个待运行任务，id 在进程内单调递增。"""

        self._counter += 1
        task = DshTask(
            task_id=f"dsh-{self._counter}", chat_id=chat_id, brief=brief, backend=backend, session=session,
        )
        self._tasks[task.task_id] = task
        self._drop_old_finished()
        return task

    def get(self, task_id: str) -> Optional[DshTask]:
        """按 id 取任务；不存在时返回 None 由调用方报错。"""

        return self._tasks.get(task_id)

    def list_all(self) -> List[DshTask]:
        """按登记顺序返回全部任务。"""

        return list(self._tasks.values())

    def list_for_chat(self, chat_id: str) -> List[DshTask]:
        """返回某个聊天登记过的任务，最新登记的在后。"""

        return [task for task in self._tasks.values() if task.chat_id == chat_id]

    def finish(self, task: DshTask, status: DshTaskStatus, *, result: str = "", error: str = "") -> None:
        """写入终态；结果与错误都原样保留，不做兜底改写。"""

        task.status = status
        if result:
            task.result = result
        task.error = error
        task.finished_at = time.time()
        self._drop_old_finished()

    def _drop_old_finished(self) -> None:
        """只清理已结束的旧任务，运行中的任务始终保留。"""

        finished = [task for task in self._tasks.values() if task.status != "running"]
        if len(finished) <= DSH_FINISHED_TASK_KEEP_COUNT:
            return
        expired = sorted(finished, key=lambda task: task.finished_at or 0.0)[: len(finished) - DSH_FINISHED_TASK_KEEP_COUNT]
        for task in expired:
            self._tasks.pop(task.task_id, None)
