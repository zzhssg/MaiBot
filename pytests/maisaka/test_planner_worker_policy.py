from src.common.prompt_i18n import load_prompt


def test_worker_policy_requires_self_dispatch():
    text = load_prompt("planner_worker_policy")

    assert "dsh_task" in text
    assert "/work" in text
