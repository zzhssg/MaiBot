import asyncio

import pytest

from src.agent.worker import pool as pool_module
from src.agent.worker.pool import WorkerPool
from src.config.config import global_config


class FakeSession:
    def __init__(self, chat_id, config, cwd):
        self.chat_id = chat_id
        self.config = config
        self.cwd = cwd
        self.alive = True
        self.closed = False
        self.prompts = []

    async def start(self):
        return None

    async def run(self, prompt, timeout):
        self.prompts.append(prompt)
        return "完成了"

    async def close(self):
        self.closed = True


@pytest.fixture
def pool_env(monkeypatch, tmp_path):
    monkeypatch.setattr(pool_module, "get_instance_root", lambda: tmp_path)
    monkeypatch.setattr(global_config.agent.worker, "workspace", str(tmp_path))
    monkeypatch.setattr(global_config.agent.worker, "max_concurrent", 2)
    monkeypatch.setattr(global_config.agent.worker, "timeout", 5.0)
    monkeypatch.setattr(global_config.agent.worker, "session_ttl_seconds", 60.0)
    monkeypatch.setattr(global_config.agent.worker, "max_sessions", 4)
    monkeypatch.setattr(pool_module, "WorkerSession", FakeSession)
    delivered = []

    async def deliver(task):
        delivered.append(task)

    return WorkerPool(deliver=deliver), delivered


@pytest.mark.asyncio
async def test_submit_runs_in_background_and_delivers(pool_env):
    pool, delivered = pool_env

    task = pool.submit(chat_id="c1", brief="读 README", screen=False)
    assert task.status == "running"
    assert task.asyncio_task is not None

    await task.asyncio_task

    assert task.status == "done"
    assert task.result == "完成了"
    assert [item.task_id for item in delivered] == [task.task_id]


@pytest.mark.asyncio
async def test_timeout_marks_task_and_still_delivers(pool_env, monkeypatch):
    pool, delivered = pool_env

    async def timeout_run(self, prompt, timeout):
        raise TimeoutError("DSH 任务超过 0 秒未完成，会话已取消")

    monkeypatch.setattr(FakeSession, "run", timeout_run)

    task = pool.submit(chat_id="c1", brief="慢任务", screen=False)
    await task.asyncio_task

    assert task.status == "timeout"
    assert delivered[0].status == "timeout"


@pytest.mark.asyncio
async def test_stop_cancels_running_task(pool_env, monkeypatch):
    pool, delivered = pool_env
    started = asyncio.Event()

    async def hang(self, prompt, timeout):
        started.set()
        await asyncio.Event().wait()

    monkeypatch.setattr(FakeSession, "run", hang)

    task = pool.submit(chat_id="c1", brief="长任务", screen=False)
    await started.wait()
    assert pool.stop("c1", task.task_id) is True
    with pytest.raises(asyncio.CancelledError):
        await task.asyncio_task

    assert task.status == "cancelled"
    assert delivered[0].task_id == task.task_id


@pytest.mark.asyncio
async def test_status_is_scoped_to_chat(pool_env):
    pool, _ = pool_env
    task = pool.submit(chat_id="c1", brief="a", screen=False)
    await task.asyncio_task

    assert pool.status("c1", task.task_id)["status"] == "done"
    with pytest.raises(ValueError, match="不属于当前聊天"):
        pool.status("c2", task.task_id)


def test_relative_workspace_is_rejected(pool_env, monkeypatch):
    pool, _ = pool_env
    monkeypatch.setattr(global_config.agent.worker, "workspace", "relative/path")

    with pytest.raises(ValueError, match="绝对路径"):
        pool.submit(chat_id="c1", brief="a", screen=False)


@pytest.mark.asyncio
async def test_close_cancels_tasks_without_delivering(pool_env, monkeypatch):
    pool, delivered = pool_env
    started = asyncio.Event()

    async def hang(self, prompt, timeout):
        started.set()
        await asyncio.Event().wait()

    monkeypatch.setattr(FakeSession, "run", hang)

    task = pool.submit(chat_id="c1", brief="长任务", screen=False)
    await started.wait()
    await pool.close()

    assert task.status == "cancelled"
    assert task.error == "进程关闭，任务已停止"
    assert delivered == []


@pytest.mark.asyncio
async def test_partial_output_survives_abnormal_stop(pool_env, monkeypatch):
    pool, delivered = pool_env

    async def partial(self, prompt, timeout):
        raise pool_module.WorkerTurnError("DSH 未正常结束（refusal）", "写了一半")

    monkeypatch.setattr(FakeSession, "run", partial)

    task = pool.submit(chat_id="c1", brief="写报告", screen=False)
    await task.asyncio_task

    assert task.status == "failed"
    assert task.result == "写了一半"
    assert delivered[0].status == "failed"


@pytest.mark.asyncio
async def test_follow_up_reuses_retained_session(pool_env, monkeypatch):
    pool, _ = pool_env
    created = []

    class CountingSession(FakeSession):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            created.append(self)

    monkeypatch.setattr(pool_module, "WorkerSession", CountingSession)

    first = pool.submit(chat_id="c1", brief="读 README", screen=False)
    await first.asyncio_task
    second = pool.submit(chat_id="c1", brief="再总结成三句", screen=False, continue_from=first.session)
    await second.asyncio_task

    assert len(created) == 1
    assert second.session == first.session
    assert len(created[0].prompts) == 2
    from src.common.prompt_i18n import load_prompt

    assert load_prompt("dsh_worker_continue").strip() in created[0].prompts[1]
    await pool.close()


@pytest.mark.asyncio
async def test_unknown_session_handle_is_rejected(pool_env):
    pool, _ = pool_env

    with pytest.raises(ValueError, match="不存在或已过期"):
        pool.submit(chat_id="c1", brief="继续", screen=False, continue_from="dsh-s99")


@pytest.mark.asyncio
async def test_failed_task_does_not_retain_session(pool_env, monkeypatch):
    pool, _ = pool_env

    async def boom(self, prompt, timeout):
        raise RuntimeError("启动失败")

    monkeypatch.setattr(FakeSession, "run", boom)

    task = pool.submit(chat_id="c1", brief="读 README", screen=False)
    await task.asyncio_task

    with pytest.raises(ValueError, match="不存在或已过期"):
        pool.submit(chat_id="c1", brief="继续", screen=False, continue_from=task.session)


@pytest.mark.asyncio
async def test_expired_session_is_closed(pool_env, monkeypatch):
    pool, _ = pool_env
    monkeypatch.setattr(global_config.agent.worker, "session_ttl_seconds", 0.01)

    task = pool.submit(chat_id="c1", brief="读 README", screen=False)
    await task.asyncio_task
    await asyncio.sleep(0.05)

    with pytest.raises(ValueError, match="不存在或已过期"):
        pool.submit(chat_id="c1", brief="继续", screen=False, continue_from=task.session)
    await asyncio.sleep(0)


@pytest.mark.asyncio
async def test_running_task_is_persisted_and_reload_marks_interrupted(pool_env, monkeypatch, tmp_path):
    pool, _ = pool_env
    monkeypatch.setattr(pool_module, "get_instance_root", lambda: tmp_path)
    started = asyncio.Event()

    async def hang(self, prompt, timeout):
        started.set()
        await asyncio.Event().wait()

    monkeypatch.setattr(FakeSession, "run", hang)

    task = pool.submit(chat_id="c1", brief="长任务", screen=False)
    await started.wait()
    await pool._flush()

    records = pool._load_interrupted()
    assert [record["task_id"] for record in records] == [task.task_id]
    assert records[0]["chat_id"] == "c1"
    assert not pool._state_path().exists()

    task.asyncio_task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task.asyncio_task


@pytest.mark.asyncio
async def test_finished_task_leaves_no_running_record(pool_env, monkeypatch, tmp_path):
    pool, _ = pool_env
    monkeypatch.setattr(pool_module, "get_instance_root", lambda: tmp_path)

    task = pool.submit(chat_id="c1", brief="读 README", screen=False)
    await task.asyncio_task
    await pool._flush()

    assert not pool._state_path().exists()
