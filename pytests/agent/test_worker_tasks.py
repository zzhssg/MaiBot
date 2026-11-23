from src.agent.worker.tasks import DSH_FINISHED_TASK_KEEP_COUNT, DshTaskRegistry


def test_create_assigns_incrementing_ids_and_tracks_chat():
    registry = DshTaskRegistry()

    first = registry.create(chat_id="c1", brief="a", backend="cli", session="dsh-s1")
    second = registry.create(chat_id="c2", brief="b", backend="desktop", session="dsh-s2")

    assert (first.task_id, second.task_id) == ("dsh-1", "dsh-2")
    assert [task.task_id for task in registry.list_for_chat("c1")] == ["dsh-1"]
    assert registry.running_count == 2


def test_finish_records_status_result_and_elapsed():
    registry = DshTaskRegistry()
    task = registry.create(chat_id="c1", brief="a", backend="cli", session="dsh-s1")

    registry.finish(task, "done", result="ok")

    assert task.status == "done"
    assert task.result == "ok"
    assert task.error == ""
    assert task.finished_at is not None
    assert registry.running_count == 0
    assert task.summary()["result_preview"] == "ok"


def test_old_finished_tasks_are_trimmed_but_running_ones_kept():
    registry = DshTaskRegistry()
    running = registry.create(chat_id="c1", brief="long", backend="cli", session="dsh-s3")
    for index in range(DSH_FINISHED_TASK_KEEP_COUNT + 5):
        task = registry.create(chat_id="c1", brief=f"t{index}", backend="cli", session=f"dsh-s{index + 4}")
        registry.finish(task, "done", result="ok")

    assert registry.get(running.task_id) is not None
    assert len(registry.list_all()) == DSH_FINISHED_TASK_KEEP_COUNT + 1
