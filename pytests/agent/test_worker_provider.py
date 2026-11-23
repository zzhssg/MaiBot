import pytest

from src.agent.worker import policy as policy_module
from src.agent.worker.provider import DshWorkerToolProvider
from src.agent.worker.tasks import DshTask
from src.config.config import global_config
from src.core.tooling import ToolAvailabilityContext, ToolExecutionContext, ToolInvocation


class FakePool:
    """只记录调用，不真的起 DSH 进程。"""

    def __init__(self) -> None:
        self.submitted = []
        self.tasks = {}

    def submit(self, *, chat_id: str, brief: str, screen: bool, continue_from: str = "") -> DshTask:
        task = DshTask(
            task_id=f"dsh-{len(self.submitted) + 1}",
            chat_id=chat_id,
            brief=brief,
            backend="desktop" if screen else "cli",
            session="dsh-s1",
        )
        self.submitted.append((chat_id, brief, screen, continue_from))
        self.tasks[task.task_id] = task
        return task

    def status(self, chat_id: str, task_id: str = ""):
        if not task_id:
            return {"running": 0, "tasks": []}
        if task_id not in self.tasks:
            raise ValueError(f"任务不存在或不属于当前聊天：{task_id}")
        return {"task_id": task_id, "status": "running"}

    def stop(self, chat_id: str, task_id: str) -> bool:
        return False


@pytest.fixture
def worker(monkeypatch):
    monkeypatch.setattr(global_config.agent.worker, "enabled", True)
    monkeypatch.setattr(global_config.agent.worker, "allow_users", [])
    monkeypatch.setattr(global_config.agent.worker, "allow_groups", [])
    monkeypatch.setattr(global_config.agent.worker, "screen_allow_users", [])
    monkeypatch.setattr(policy_module, "is_owner_chat", lambda session_id: session_id == "owner")
    pool = FakePool()
    return DshWorkerToolProvider(pool=pool), pool


def dm(session_id: str = "s1", user_id: str = "42") -> ToolExecutionContext:
    return ToolExecutionContext(session_id=session_id, platform="qq", user_id=user_id, is_group_chat=False)


def group(group_id: str = "99") -> ToolAvailabilityContext:
    return ToolAvailabilityContext(session_id="s2", platform="qq", group_id=group_id, is_group_chat=True)


@pytest.mark.asyncio
async def test_tools_hidden_when_disabled(worker, monkeypatch):
    provider, _ = worker
    monkeypatch.setattr(global_config.agent.worker, "enabled", False)

    assert await provider.list_tools(dm()) == []


@pytest.mark.asyncio
async def test_stranger_private_chat_gets_no_tools(worker):
    provider, _ = worker

    assert await provider.list_tools(dm()) == []
    assert [spec.name for spec in await provider.list_tools(dm(session_id="owner"))] == [
        "dsh_task",
        "dsh_status",
        "dsh_stop",
    ]


@pytest.mark.asyncio
async def test_allowlisted_user_and_group_see_tools(worker, monkeypatch):
    provider, _ = worker
    monkeypatch.setattr(global_config.agent.worker, "allow_users", ["qq:42"])
    monkeypatch.setattr(global_config.agent.worker, "allow_groups", ["qq:99"])

    assert len(await provider.list_tools(dm())) == 3
    assert len(await provider.list_tools(group())) == 3
    assert await provider.list_tools(group("100")) == []


@pytest.mark.asyncio
async def test_empty_brief_is_rejected(worker):
    provider, pool = worker

    result = await provider.invoke(ToolInvocation(tool_name="dsh_task", arguments={"brief": "  "}), dm("owner"))

    assert result.success is False
    assert "brief" in result.error_message
    assert pool.submitted == []


@pytest.mark.asyncio
async def test_screen_requires_explicit_allowlist(worker, monkeypatch):
    provider, pool = worker

    denied = await provider.invoke(
        ToolInvocation(tool_name="dsh_task", arguments={"brief": "点开设置", "screen": True}), dm("owner")
    )
    assert denied.success is False
    assert "屏幕" in denied.error_message
    assert pool.submitted == []

    monkeypatch.setattr(global_config.agent.worker, "screen_allow_users", ["qq:42"])
    allowed = await provider.invoke(
        ToolInvocation(tool_name="dsh_task", arguments={"brief": "点开设置", "screen": True}), dm("owner")
    )
    assert allowed.success is True
    assert pool.submitted == [("owner", "点开设置", True, "")]


@pytest.mark.asyncio
async def test_status_rejects_unknown_task(worker):
    provider, _ = worker

    result = await provider.invoke(ToolInvocation(tool_name="dsh_status", arguments={"task_id": "dsh-9"}), dm("owner"))

    assert result.success is False
    assert "dsh-9" in result.error_message


@pytest.mark.asyncio
async def test_stop_reports_missing_task(worker):
    provider, _ = worker

    result = await provider.invoke(ToolInvocation(tool_name="dsh_stop", arguments={"task_id": "dsh-1"}), dm("owner"))

    assert result.success is False
    assert "dsh-1" in result.error_message
