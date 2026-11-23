from types import SimpleNamespace

import pytest

from src.chat.replyer import reply_model_route
from src.chat.replyer.reply_model_route import (
    NON_THINKING,
    THINKING,
    classify_thinking_mode,
    select_reply_model_name,
)
from src.config.model_configs import ModelInfo


def _model(name: str, extra_params: dict[str, object]) -> ModelInfo:
    return ModelInfo(model_type="llm", model_identifier=f"test-{name}", name=name, extra_params=extra_params)


THINK_MODEL = _model("reply-think", {"thinking": {"type": "enabled"}, "reasoning_effort": "high"})
FAST_MODEL = _model("reply-fast", {"thinking": {"type": "disabled"}})


@pytest.mark.parametrize(
    ("extra_params", "expected"),
    [
        ({"thinking": {"type": "enabled"}}, THINKING),
        ({"thinking": {"type": "disabled"}}, NON_THINKING),
        ({"thinking": True}, THINKING),
        ({"thinking": False}, NON_THINKING),
        ({"enable_thinking": True}, THINKING),
        ({"enable_thinking": False}, NON_THINKING),
        ({"reasoning_effort": "high"}, THINKING),
        ({"reasoning_effort": "none"}, NON_THINKING),
        ({}, None),
    ],
)
def test_classify_thinking_mode(extra_params: dict[str, object], expected: str | None) -> None:
    assert classify_thinking_mode(_model("m", extra_params)) == expected


def _patch_catalog(monkeypatch: pytest.MonkeyPatch, model_list: list[str]) -> None:
    monkeypatch.setattr(
        reply_model_route,
        "model_config",
        SimpleNamespace(
            models=[THINK_MODEL, FAST_MODEL],
            model_task_config=SimpleNamespace(replyer=SimpleNamespace(model_list=model_list)),
        ),
    )


@pytest.mark.parametrize("reply_style", ["简短表达", "正常回复", ""])
def test_short_and_normal_replies_use_fast_model(monkeypatch: pytest.MonkeyPatch, reply_style: str) -> None:
    _patch_catalog(monkeypatch, ["reply-think", "reply-fast"])

    assert select_reply_model_name({"reply_style": reply_style}) == "reply-fast"


def test_long_replies_keep_thinking_model(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_catalog(monkeypatch, ["reply-think", "reply-fast"])

    assert select_reply_model_name({"reply_style": "长回复"}) == "reply-think"


def test_single_model_list_is_left_alone(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_catalog(monkeypatch, ["reply-think"])

    assert select_reply_model_name({"reply_style": "简短表达"}) is None


def test_unclassified_models_fall_back_to_original_selection(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        reply_model_route,
        "model_config",
        SimpleNamespace(
            models=[_model("a", {}), _model("b", {})],
            model_task_config=SimpleNamespace(replyer=SimpleNamespace(model_list=["a", "b"])),
        ),
    )

    assert select_reply_model_name({"reply_style": "简短表达"}) is None
