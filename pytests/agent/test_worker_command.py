import pytest

from src.agent.worker import policy as policy_module
from src.agent.worker.command import build_work_task_text, parse_work_command
from src.config.config import global_config


def test_parse_work_command_extracts_content():
    assert parse_work_command("/work 读一下 README") == "读一下 README"
    assert parse_work_command("  /work  修一下代码 ") == "修一下代码"
    assert parse_work_command("/work") == ""
    assert parse_work_command("/worker 不是指令") is None
    assert parse_work_command("随便聊聊") is None
    assert parse_work_command(None) is None


def test_work_task_text_requires_dispatch():
    text = build_work_task_text("读一下 README")

    assert "读一下 README" in text
    assert "dsh_task" in text


def test_worker_allowed_owner_and_allowlists(monkeypatch):
    monkeypatch.setattr(global_config.agent.worker, "enabled", True)
    monkeypatch.setattr(global_config.agent.worker, "allow_users", ["qq:42"])
    monkeypatch.setattr(global_config.agent.worker, "allow_groups", [])
    monkeypatch.setattr(policy_module, "is_owner_chat", lambda session_id: session_id == "owner")

    assert policy_module.worker_allowed(session_id="owner", platform="qq", user_id="1") is True
    assert policy_module.worker_allowed(session_id="s1", platform="qq", user_id="42") is True
    assert policy_module.worker_allowed(session_id="s1", platform="qq", user_id="43") is False
    assert policy_module.worker_allowed(session_id="s2", platform="qq", user_id="42", group_id="99", is_group=True) is False


def test_worker_allowed_respects_switch(monkeypatch):
    monkeypatch.setattr(global_config.agent.worker, "enabled", False)
    monkeypatch.setattr(policy_module, "is_owner_chat", lambda session_id: True)

    assert policy_module.worker_allowed(session_id="owner", platform="qq", user_id="1") is False


def test_screen_requires_explicit_list(monkeypatch):
    monkeypatch.setattr(global_config.agent.worker, "screen_allow_users", [])
    assert policy_module.screen_allowed(platform="qq", user_id="42") is False

    monkeypatch.setattr(global_config.agent.worker, "screen_allow_users", ["qq:42"])
    assert policy_module.screen_allowed(platform="qq", user_id="42") is True


@pytest.mark.parametrize("text", ["/Work 大写", "/work\t制表符"])
def test_non_matching_forms_are_not_commands(text):
    assert parse_work_command(text) is None
