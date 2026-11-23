"""入站图片描述预取。

VLM 识图原本要等 Planner 装配上下文时才触发，等待直接叠在回复关键路径上。
这里在消息批次通过发言判定、仍在等防抖窗口时先提交识别任务，把等待挪到模型
请求之前；描述按图片哈希永久缓存，同一张图不会重复识别。
"""

from typing import TYPE_CHECKING, Iterable, Iterator, List

from src.common.data_models.message_component_data_model import (
    ForwardNodeComponent,
    ImageComponent,
    StandardMessageComponents,
)
from src.common.logger import get_logger

if TYPE_CHECKING:
    from src.chat.message_receive.message import SessionMessage

logger = get_logger("image_prefetch")


def _iter_images(components: Iterable[StandardMessageComponents]) -> Iterator[ImageComponent]:
    """递归遍历消息组件里的图片，转发消息内部同样覆盖。"""

    for component in components:
        if isinstance(component, ImageComponent):
            yield component
        elif isinstance(component, ForwardNodeComponent):
            for forward_component in component.forward_components:
                yield from _iter_images(forward_component.content)


def pending_images(messages: Iterable["SessionMessage"]) -> List[ImageComponent]:
    """收集尚未识别、仍带原始字节的图片组件。"""

    pending: List[ImageComponent] = []
    for message in messages:
        for component in _iter_images(message.raw_message.components):
            if component.content.strip() or not component.binary_data:
                continue
            pending.append(component)
    return pending


async def prefetch_images(messages: Iterable["SessionMessage"], *, log_prefix: str = "") -> int:
    """为待处理消息里的图片提前提交后台识别，返回提交数量。"""

    from src.chat.image_system.image_manager import image_manager, is_image_recognition_available

    if not is_image_recognition_available():
        return 0

    submitted = 0
    for component in pending_images(messages):
        try:
            # wait_for_build=False 只登记图片并调度后台识别，不阻塞消息登记。
            await image_manager.get_image_description(
                image_bytes=component.binary_data,
                wait_for_build=False,
            )
            submitted += 1
        except Exception as exc:
            logger.warning(f"{log_prefix} 图片描述预取失败: {exc}")
    if submitted:
        logger.debug(f"{log_prefix} 已预取 {submitted} 张图片的识别任务")
    return submitted
