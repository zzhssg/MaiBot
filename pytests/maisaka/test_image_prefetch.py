from types import SimpleNamespace

from src.chat.image_system.prefetch import pending_images
from src.common.data_models.message_component_data_model import (
    ForwardComponent,
    ForwardNodeComponent,
    ImageComponent,
    MessageSequence,
    TextComponent,
)


def _image(*, binary_data: bytes = b"raw-image", content: str = "") -> ImageComponent:
    return ImageComponent(binary_hash="", binary_data=binary_data, content=content)


def _message(*components) -> SimpleNamespace:
    return SimpleNamespace(raw_message=MessageSequence(list(components)))


def test_collects_only_unrecognized_images_with_bytes() -> None:
    recognized = _image(content="[图片：猫]")
    empty = _image(binary_data=b"")
    fresh = _image()

    pending = pending_images([_message(TextComponent("看这个"), recognized, empty, fresh)])

    assert pending == [fresh]


def test_collects_images_inside_forward_nodes() -> None:
    forwarded_image = _image()
    forward_node = ForwardNodeComponent(
        [ForwardComponent(user_nickname="群友", message_id="f1", content=[forwarded_image])],
    )

    pending = pending_images([_message(forward_node)])

    assert pending == [forwarded_image]


def test_message_without_images_yields_nothing() -> None:
    assert pending_images([_message(TextComponent("纯文字"))]) == []
