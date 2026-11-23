"""按回复篇幅选择思考或非思考模型。

Planner 每轮都会给出 ``reply_style``。短回复再走思考模型只会把首字延迟拉长，
长回复才需要推理链；这里在请求前按模型配置里的 ``extra_params`` 识别档位，
只在实际配置了两种档位时改选模型，判断不出档位时保持原有随机选择。
"""

from typing import Any, Optional

from src.config.config import model_config
from src.config.model_configs import ModelInfo

THINKING = "thinking"
NON_THINKING = "non_thinking"
LONG_REPLY_STYLE = "长回复"


def classify_thinking_mode(model_info: ModelInfo) -> Optional[str]:
    """按请求体额外参数判断模型是否开启思考；无法判断时返回 None。"""

    extra_params = model_info.extra_params or {}
    thinking = extra_params.get("thinking")
    if isinstance(thinking, dict):
        thinking_type = str(thinking.get("type") or "").strip().lower()
        if thinking_type == "enabled":
            return THINKING
        if thinking_type == "disabled":
            return NON_THINKING
    elif isinstance(thinking, bool):
        return THINKING if thinking else NON_THINKING

    enable_thinking = extra_params.get("enable_thinking")
    if isinstance(enable_thinking, bool):
        return THINKING if enable_thinking else NON_THINKING

    reasoning_effort = extra_params.get("reasoning_effort")
    if isinstance(reasoning_effort, str):
        normalized_effort = reasoning_effort.strip().lower()
        if normalized_effort in {"", "none", "off", "disabled"}:
            return NON_THINKING
        return THINKING
    return None


def select_reply_model_name(reply_tool_args: dict[str, Any]) -> Optional[str]:
    """按本次回复篇幅挑模型；不需要改选或无法判断时返回 None。"""

    reply_style = str(reply_tool_args.get("reply_style") or "").strip()
    model_names = [name for name in model_config.model_task_config.replyer.model_list if name.strip()]
    if len(model_names) < 2:
        return None

    models_by_name = {model.name: model for model in model_config.models}
    wanted_mode = THINKING if reply_style == LONG_REPLY_STYLE else NON_THINKING
    for name in model_names:
        model_info = models_by_name.get(name)
        if model_info is not None and classify_thinking_mode(model_info) == wanted_mode:
            return name
    return None
