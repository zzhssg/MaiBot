"""Planner 一次性注入结果的缓存。

Planner 每轮都会重新装配启发式记忆、人物画像、图片记忆和黑话参考。同一批
消息在没有新增时，这些内容不会变化，重查数据库只会把等待叠在模型请求之前。
缓存只在触发消息或待处理消息集变化时失效，保证注入内容与实际上下文一致。
"""

from typing import TYPE_CHECKING, Iterable, List, Optional, Tuple

if TYPE_CHECKING:
    from src.chat.message_receive.message import SessionMessage


InjectionCacheKey = Tuple[str, Tuple[str, ...]]


class PlannerInjectionCache:
    """按“触发消息 + 待处理消息集”缓存一轮思考内的注入文本。"""

    def __init__(self) -> None:
        self._key: Optional[InjectionCacheKey] = None
        self._messages: List[str] = []

    @staticmethod
    def build_key(anchor_message_id: str, source_messages: Iterable["SessionMessage"]) -> InjectionCacheKey:
        """用触发消息编号和待处理消息编号构造缓存键。"""

        return (
            str(anchor_message_id or ""),
            tuple(str(message.message_id or "") for message in source_messages),
        )

    def get(self, key: InjectionCacheKey) -> Optional[List[str]]:
        """返回同一批消息上一次算好的注入文本；键不匹配时返回 None。"""

        if key != self._key:
            return None
        return list(self._messages)

    def put(self, key: InjectionCacheKey, messages: Iterable[str]) -> None:
        """记录本批消息的注入文本。"""

        self._key = key
        self._messages = list(messages)

    def clear(self) -> None:
        """逻辑回合结束时释放缓存，避免跨回合复用旧内容。"""

        self._key = None
        self._messages = []
