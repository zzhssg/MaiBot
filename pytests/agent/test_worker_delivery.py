from src.agent.worker.delivery import (
    MAX_RESULT_CHARS, build_delivery_text, build_interrupted_text, build_progress_text,
)
from src.agent.worker.tasks import DshTask


def make_task(**overrides):
    task = DshTask(task_id="dsh-3", chat_id="c1", brief="改一下 README\n并跑测试", backend="cli", session="dsh-s1")
    for name, value in overrides.items():
        setattr(task, name, value)
    return task


def test_delivery_carries_task_identity_and_result():
    task = make_task(result="改了 README 的前两行")

    text = build_delivery_text(task)

    assert "dsh-3" in text
    assert "dsh-s1" in text
    assert "改一下 README 并跑测试" in text
    assert "改了 README 的前两行" in text


def test_delivery_truncates_long_results():
    task = make_task(result="x" * (MAX_RESULT_CHARS + 10))

    text = build_delivery_text(task)

    assert "结果过长" in text
    assert "x" * (MAX_RESULT_CHARS + 10) not in text


def test_delivery_exposes_error_when_there_is_no_output():
    task = make_task(status="failed", error="TimeoutError: boom")

    text = build_delivery_text(task)

    assert "没有正文输出" in text
    assert "TimeoutError: boom" in text


def test_interrupted_text_carries_task_and_brief():
    text = build_interrupted_text({"task_id": "dsh-7", "brief": "改一下 README"})

    assert "dsh-7" in text
    assert "改一下 README" in text


def test_progress_text_names_task_and_action():
    task = make_task(progress="读文件：README", started_at=__import__("time").time() - 75)

    text = build_progress_text(task)

    assert "dsh-3" in text
    assert "读文件：README" in text
    assert "1 分 1" in text or "1 分 15" in text
