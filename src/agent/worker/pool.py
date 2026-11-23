"""DSH Worker 池：任务独立会话，结束后按 TTL 保留给同一件事的追问。"""

from collections.abc import Awaitable, Callable
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

import asyncio
import time

from src.agent.config import AgentConfig
from src.agent.worker.delivery import deliver_task_result
from src.agent.worker.session import WorkerSession, WorkerTimeout, WorkerTurnError
from src.agent.worker.tasks import DshTask, DshTaskRegistry
from src.common.json_storage import read_json, write_json
from src.common.logger import get_logger
from src.common.paths import get_instance_root
from src.common.prompt_i18n import load_prompt
from src.config.config import global_config

logger = get_logger("agent.worker.pool")


@dataclass(slots=True)
class _RetainedSession:
    """任务结束后仍保持连接的会话，等同一件事的追问。"""

    handle: str
    chat_id: str
    backend: str
    session: WorkerSession
    lock: asyncio.Lock
    expires_at: float
    last_task_id: str


class WorkerPool:
    """一个进程内共享的 worker 池：任务默认新开会话，结束后保留一小段时间供追问。"""

    def __init__(self, deliver: Optional[Callable[[DshTask], Awaitable[None]]] = None) -> None:
        self._deliver = deliver or deliver_task_result
        self._registry = DshTaskRegistry()
        self._retained: Dict[str, _RetainedSession] = {}
        self._session_counter = 0
        self._semaphore: Optional[asyncio.Semaphore] = None
        self._semaphore_size = 0
        self._inflight = 0
        self._closing = False
        self._closed = False
        self._started = False
        self._persist_lock = asyncio.Lock()

    async def start(self) -> None:
        """加载上次进程遗留的在途任务，等聊天循环就绪后回送中断说明。"""

        if self._started:
            return
        self._started = True
        records = await asyncio.to_thread(self._load_interrupted)
        if not records:
            return
        asyncio.create_task(self._announce_interrupted(records), name="agent.worker.interrupted")

    def submit(self, *, chat_id: str, brief: str, screen: bool, continue_from: str = "") -> DshTask:
        """登记并启动一个后台任务；continue_from 复用保留会话，否则新开一个。"""

        if self._closed:
            raise RuntimeError("DSH Worker 已关闭")
        self._sweep()
        config = global_config.agent
        workspace = self._workspace(config)
        self._ensure_semaphore()
        backend = "desktop" if screen else "cli"
        retained = self._take(chat_id, continue_from, backend) if continue_from else None
        handle = retained.handle if retained is not None else self._new_handle()
        task = self._registry.create(
            chat_id=chat_id, brief=brief, backend=backend, session=handle,
        )
        task.asyncio_task = asyncio.create_task(
            self._run(task, workspace, retained), name=f"agent.worker:{task.task_id}",
        )
        self._schedule_flush()
        return task

    def status(self, chat_id: str, task_id: str = "") -> Dict[str, Any]:
        """查询单个任务或当前聊天的最近任务；跨聊天查询直接报错。"""

        self._sweep()
        if task_id:
            task = self._registry.get(task_id)
            if task is None or task.chat_id != chat_id:
                raise ValueError(f"任务不存在或不属于当前聊天：{task_id}")
            detail = task.summary()
            detail["result"] = task.result[:2000]
            detail["result_chars"] = len(task.result)
            detail["session_retained"] = task.session in self._retained
            if task.status == "running":
                detail["notice"] = "任务仍在运行；结果会自动作为内部消息送回，不要轮询。"
            return detail
        tasks: List[DshTask] = self._registry.list_for_chat(chat_id)
        sessions = [
            {"session": item.handle, "expires_in": max(0, round(item.expires_at - time.time()))}
            for item in self._retained.values() if item.chat_id == chat_id
        ]
        return {
            "running": sum(1 for task in tasks if task.status == "running"),
            "sessions": sorted(sessions, key=lambda item: item["expires_in"]),
            "tasks": [task.summary() for task in reversed(tasks)],
        }

    def stop(self, chat_id: str, task_id: str) -> bool:
        """取消仍在运行的任务；任务不存在、已结束或跨聊天时返回 False。"""

        task = self._registry.get(task_id)
        if task is None or task.chat_id != chat_id or task.status != "running" or task.asyncio_task is None:
            return False
        task.asyncio_task.cancel()
        self._registry.finish(task, "cancelled", error="任务被取消")
        return True

    async def close(self) -> None:
        """停止全部任务并关闭保留会话；进程退出时由 runtime.graceful_shutdown 调用。"""

        if self._closed:
            return
        self._closed = True
        self._closing = True
        running = [
            task.asyncio_task for task in self._registry.list_all()
            if task.status == "running" and task.asyncio_task is not None
        ]
        for pending in running:
            pending.cancel()
        await asyncio.gather(*running, return_exceptions=True)
        # 还没开始的协程被取消后不会进入 _run 的收尾，这里统一补终态，避免写成在途任务。
        for task in self._registry.list_all():
            if task.status == "running":
                self._registry.finish(task, "cancelled", error="进程关闭，任务已停止")
        retained = list(self._retained.values())
        self._retained.clear()
        for item in retained:
            with suppress(Exception):
                await item.session.close()
        with suppress(Exception):
            await asyncio.to_thread(self._write_state)

    async def _run(self, task: DshTask, workspace: Path, retained: Optional[_RetainedSession]) -> None:
        """执行任务并落终态；成功的会话按 TTL 保留，失败或取消的会话直接关闭。"""

        config = global_config.agent
        session = retained.session if retained is not None else None
        lock = retained.lock if retained is not None else asyncio.Lock()
        keep = False
        self._inflight += 1
        try:
            async with self._semaphore_or_raise():
                async with lock:
                    if session is None:
                        session = WorkerSession(
                            chat_id=task.chat_id,
                            config=self._backend_config(config, task.backend),
                            cwd=workspace,
                        )
                        await session.start()
                    task.result = await session.run(
                        self._prompt(task, continuation=retained is not None), config.worker.timeout,
                    )
            self._registry.finish(task, "done", result=task.result)
            keep = True
        except TimeoutError as exc:
            if isinstance(exc, WorkerTimeout):
                task.result = exc.text
            self._registry.finish(task, "timeout", error=str(exc))
        except asyncio.CancelledError:
            self._registry.finish(task, "cancelled", error="进程关闭，任务已停止" if self._closing else "任务被取消")
            if not self._closing:
                await self._deliver_safely(task)
            raise
        except Exception as exc:
            if isinstance(exc, WorkerTurnError):
                task.result = exc.text
            logger.exception(f"DSH worker 任务失败: task_id={task.task_id}")
            self._registry.finish(task, "failed", error=f"{type(exc).__name__}: {exc}")
        finally:
            self._inflight -= 1
            if session is not None:
                if keep and not self._closing:
                    self._retain(task, session, lock)
                else:
                    with suppress(Exception):
                        await session.close()
            self._schedule_flush()
        await self._deliver_safely(task)

    def _retain(self, task: DshTask, session: WorkerSession, lock: asyncio.Lock) -> None:
        """把成功任务的会话放回保留区，并刷新过期时间。"""

        ttl = global_config.agent.worker.session_ttl_seconds
        self._retained[task.session] = _RetainedSession(
            handle=task.session,
            chat_id=task.chat_id,
            backend=task.backend,
            session=session,
            lock=lock,
            expires_at=time.time() + ttl,
            last_task_id=task.task_id,
        )
        self._enforce_max()

    def _take(self, chat_id: str, handle: str, backend: str) -> _RetainedSession:
        """取回待复用的会话；不存在、跨聊天、后端不符或连接失效都直接报错。"""

        retained = self._retained.pop(handle, None)
        if retained is None:
            raise ValueError(f"会话 {handle} 不存在或已过期，重新派发一个任务即可。")
        if retained.chat_id != chat_id:
            self._retained[handle] = retained
            raise ValueError(f"会话 {handle} 不属于当前聊天。")
        if retained.backend != backend:
            self._retained[handle] = retained
            raise ValueError(f"会话 {handle} 的后端是 {retained.backend}，不能用于 {backend} 任务。")
        if not retained.session.alive:
            self._close_soon(retained.session)
            raise ValueError(f"会话 {handle} 的连接已失效，重新派发一个任务即可。")
        return retained

    def _enforce_max(self) -> None:
        limit = max(1, global_config.agent.worker.max_sessions)
        while len(self._retained) > limit:
            oldest = min(self._retained.values(), key=lambda item: item.expires_at)
            self._retained.pop(oldest.handle, None)
            self._close_soon(oldest.session)

    def _sweep(self) -> None:
        now = time.time()
        for handle, item in list(self._retained.items()):
            if item.expires_at <= now:
                self._retained.pop(handle, None)
                self._close_soon(item.session)

    def _close_soon(self, session: WorkerSession) -> None:
        asyncio.create_task(self._close_quietly(session), name="agent.worker.close")

    async def _close_quietly(self, session: WorkerSession) -> None:
        with suppress(Exception):
            await session.close()

    def _new_handle(self) -> str:
        self._session_counter += 1
        return f"dsh-s{self._session_counter}"

    def _state_path(self) -> Path:
        return get_instance_root() / "data" / "agent" / "worker" / "state.json"

    def _write_state(self) -> None:
        """只记录仍在运行的任务；正常结束或正常关停都会把它清掉。"""

        running = [
            {
                "task_id": task.task_id,
                "chat_id": task.chat_id,
                "brief": task.brief[:500],
                "backend": task.backend,
                "session": task.session,
                "started_at": task.started_at,
            }
            for task in self._registry.list_all() if task.status == "running"
        ]
        path = self._state_path()
        if not running:
            with suppress(OSError):
                path.unlink()
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        write_json(path, {"version": 1, "running": running})

    def _load_interrupted(self) -> List[Dict[str, Any]]:
        """读取上次遗留的运行记录并删除状态文件，避免重复通报。"""

        path = self._state_path()
        if not path.exists():
            return []
        try:
            payload = read_json(path)
        except Exception:
            logger.warning(f"DSH worker 上次运行状态损坏，已忽略: {path}", exc_info=True)
            with suppress(OSError):
                path.unlink()
            return []
        records = payload.get("running") if isinstance(payload, dict) else None
        if not isinstance(records, list):
            logger.warning(f"DSH worker 上次运行状态格式不符，已忽略: {path}")
            with suppress(OSError):
                path.unlink()
            return []
        valid = [
            record for record in records
            if isinstance(record, dict) and isinstance(record.get("chat_id"), str) and isinstance(record.get("task_id"), str)
        ]
        with suppress(OSError):
            path.unlink()
        return valid

    def _schedule_flush(self) -> None:
        if self._closing:
            return
        asyncio.create_task(self._flush(), name="agent.worker.persist")

    async def _flush(self) -> None:
        async with self._persist_lock:
            try:
                await asyncio.to_thread(self._write_state)
            except Exception:
                logger.exception("DSH worker 运行状态写入失败")

    async def _announce_interrupted(self, records: List[Dict[str, Any]]) -> None:
        """启动后给原聊天补一条中断说明；运行时还没就绪就等几秒再试。"""

        from src.chat.heart_flow.heartflow_manager import heartflow_manager

        from src.agent.worker.delivery import build_interrupted_text

        await asyncio.sleep(3)
        for record in records:
            if self._closing:
                return
            try:
                runtime = await heartflow_manager.get_or_create_heartflow_chat(record["chat_id"])
                runtime.enqueue_internal_task(
                    source_kind="dsh_worker_interrupted",
                    text=build_interrupted_text(record),
                    reason="DSH 任务被中断",
                )
            except Exception:
                logger.exception(f"DSH worker 中断说明投递失败: task_id={record.get('task_id')}")

    async def _deliver_safely(self, task: DshTask) -> None:
        """回送失败只记日志：任务本身已经结束，不能因为聊天已停止而改变任务结论。"""

        try:
            await self._deliver(task)
        except Exception:
            logger.exception(f"DSH worker 结果回送失败: task_id={task.task_id}")

    def _prompt(self, task: DshTask, *, continuation: bool) -> str:
        note = load_prompt("dsh_worker_continue").strip() if continuation else ""
        return load_prompt(
            "dsh_worker_task", task_id=task.task_id, brief=task.brief, continuation_note=note,
        ).strip()

    def _backend_config(self, config: AgentConfig, backend: str) -> AgentConfig:
        """screen 任务固定走 Desktop 桥接；其余任务沿用 [agent] 的连接设置。"""

        if backend == "cli" or config.connection == "dsh_desktop":
            return config.model_copy(deep=True)
        return config.model_copy(update={"connection": "dsh_desktop"}, deep=True)

    def _workspace(self, config: AgentConfig) -> Path:
        """只接受已存在的绝对路径；留空时才由麦麦创建自己的默认目录。"""

        raw = config.worker.workspace.strip()
        if not raw:
            path = get_instance_root() / "data" / "agent" / "worker" / "workspace"
            path.mkdir(parents=True, exist_ok=True)
            return path
        path = Path(raw)
        if not path.is_absolute():
            raise ValueError(f"worker.workspace 必须是绝对路径：{raw}")
        if not path.is_dir():
            raise ValueError(f"worker.workspace 不是已存在的目录：{raw}")
        return path

    def _ensure_semaphore(self) -> None:
        """并发上限变动时重建信号量；有任务在跑时保持旧值，避免上限瞬间翻倍。"""

        size = global_config.agent.worker.max_concurrent
        if self._semaphore is not None and (self._semaphore_size == size or self._inflight > 0):
            return
        self._semaphore = asyncio.Semaphore(size)
        self._semaphore_size = size

    def _semaphore_or_raise(self) -> asyncio.Semaphore:
        if self._semaphore is None:
            raise RuntimeError("DSH Worker 并发控制尚未初始化")
        return self._semaphore


worker_pool = WorkerPool()
