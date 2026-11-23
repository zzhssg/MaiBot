from types import SimpleNamespace

from src.agent.worker.attachment import build_attachment_hint, has_file_attachment
from src.common.data_models.message_component_data_model import FileComponent, TextComponent


def message_with(*components):
    return SimpleNamespace(raw_message=SimpleNamespace(components=list(components)))


def test_detects_file_components_only():
    assert has_file_attachment(message_with(FileComponent(name="a.pdf"))) is True
    assert has_file_attachment(message_with(TextComponent("hi"))) is False


def test_hint_points_at_worker():
    text = build_attachment_hint()

    assert "dsh_task" in text
    assert text
