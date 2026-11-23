import asyncio

import pytest

from src.agent.config import AgentConfig
from src.agent.worker import session as session_module
from src.agent.worker.session import WorkerSession


class FakeConnection:
    """替身只实现 WorkerSession 真正调用到的协议。"""

    def __init__(self, update, stop_reason="end_turn", hang=False):
        self.update = update
        self.stop_reason = stop_reason
        self.hang = hang
        self.failure = None
        self.mount = "unset"
        self.mcp_port = "unset"
        self.closed = False
        self.notified = []

    async def initialize(self, config, cwd, client_name, *, mcp_port=None):
        self.mcp_port = mcp_port
        return {"mcpCapabilities": {}}

    async def open_session(self, cwd, mount, session_id, timeout):
        self.mount = mount
        return {"sessionId": "s1"}

    async def select_model(self, config, session, session_id):
        return None

    async def request(self, method, params, timeout=None):
        if method != "session/prompt":
            raise AssertionError(method)
        if self.hang:
            await asyncio.Event().wait()
        await self.update({
            "sessionId": "s1",
            "update": {"sessionUpdate": "agent_message_chunk", "content": {"type": "text", "text": "done"}},
        })
        return {"stopReason": self.stop_reason}

    async def notify(self, method, params):
        self.notified.append(method)

    async def close(self, timeout):
        self.closed = True


def install(monkeypatch, **kwargs):
    created = []

    def factory(update):
        connection = FakeConnection(update, **kwargs)
        created.append(connection)
        return connection

    monkeypatch.setattr(session_module, "ACPConnection", factory)
    return created


@pytest.mark.asyncio
async def test_start_creates_session_without_mcp(monkeypatch, tmp_path):
    created = install(monkeypatch)
    session = WorkerSession(chat_id="c1", config=AgentConfig(acp_timeout=1), cwd=tmp_path)

    await session.start()

    assert session.session_id == "s1"
    assert created[0].mcp_port is None
    assert created[0].mount is None


@pytest.mark.asyncio
async def test_run_collects_assistant_text(monkeypatch, tmp_path):
    install(monkeypatch)
    session = WorkerSession(chat_id="c1", config=AgentConfig(acp_timeout=1), cwd=tmp_path)
    await session.start()

    assert await session.run("hi", timeout=5) == "done"


@pytest.mark.asyncio
async def test_run_rejects_abnormal_stop_reason(monkeypatch, tmp_path):
    install(monkeypatch, stop_reason="refusal")
    session = WorkerSession(chat_id="c1", config=AgentConfig(acp_timeout=1), cwd=tmp_path)
    await session.start()

    with pytest.raises(RuntimeError, match="未正常结束"):
        await session.run("hi", timeout=5)


@pytest.mark.asyncio
async def test_timeout_cancels_session_and_closes_connection(monkeypatch, tmp_path):
    created = install(monkeypatch, hang=True)
    session = WorkerSession(chat_id="c1", config=AgentConfig(acp_timeout=0.05), cwd=tmp_path)
    await session.start()

    with pytest.raises(TimeoutError):
        await session.run("hi", timeout=0.01)

    assert created[0].notified == ["session/cancel"]
    assert created[0].closed is True


@pytest.mark.asyncio
async def test_abnormal_stop_keeps_partial_text(monkeypatch, tmp_path):
    install(monkeypatch, stop_reason="refusal")
    session = WorkerSession(chat_id="c1", config=AgentConfig(acp_timeout=1), cwd=tmp_path)
    await session.start()

    with pytest.raises(session_module.WorkerTurnError) as excinfo:
        await session.run("hi", timeout=5)

    assert excinfo.value.text == "done"
