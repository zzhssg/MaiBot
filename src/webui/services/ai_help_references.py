"""答疑组合检索中的少量维护者核实参考，补足官方文档未覆盖的具体接入与运行时行为。"""

from typing import Dict, List, Tuple

from .ai_search_models import AISearchSource


# 每组至少命中一个词才返回该条参考，避免把通用排障资料塞进无关问答。
_REFERENCES: Dict[str, Tuple[Tuple[Tuple[str, ...], ...], AISearchSource, str]] = {
    "help:ollama": (
        (("ollama",),),
        AISearchSource(title="Ollama · OpenAI compatibility", url="https://docs.ollama.com/api/openai-compatibility"),
        "For a local Ollama service on the same host as the MaiBot process, the OpenAI-compatible Base URL "
        "is http://localhost:11434/v1/ (also http://127.0.0.1:11434/v1/). If MaiBot runs in a separate container "
        "or on another host, use an Ollama address reachable from MaiBot; localhost refers to MaiBot's own network "
        "namespace. Ollama's SDK examples use a dummy API key, which the local Ollama service ignores. "
        "In MaiBot WebUI → 模型配置 / Model Management, add the provider with client_type=openai, auth_type=none "
        "and an empty api_key. Add a model with the actual Ollama model_identifier and set its api_provider to "
        "that provider. Use the provider connection test, then send a model test request. Assign the model to a "
        "task only after confirming that the request succeeds.",
    ),
    "help:nginx-websocket": (
        (("nginx", "反代", "reverse proxy", "リバースプロキシ"), ("websocket", "ws://", "wss", "握手", "https")),
        AISearchSource(title="NGINX · WebSocket proxying", url="https://nginx.org/en/docs/http/websocket.html"),
        "If an HTTPS WebUI tries ws:// and the browser blocks mixed content, first inspect the actual URL in "
        "Developer Tools → Network → WS. The browser-facing connection must use wss://; fix the client or public "
        "URL before debugging the upstream handshake. When wss:// reaches NGINX, check that the same proxy route "
        "forwards Upgrade and Connection headers. The linked NGINX documentation supports this proxy step; "
        "the mixed-content diagnosis follows from the reported browser URL. A successful upgrade returns HTTP 101 Switching "
        "Protocols. Verify a live log update or chat event after the handshake.",
    ),
    "help:dsh-worker": (
        (
            ("dsh", "worker", "工程能力", "后台执行", "后台任务", "电脑", "写插件", "computer"),
            ("配置", "开启", "启用", "设置", "怎么用", "怎么让", "安装", "setup", "enable"),
        ),
        AISearchSource(
            title="MaiBot · DSH Worker 接入说明",
            url="https://github.com/Mai-with-u/MaiBot/blob/main/docs/dsh-worker.md",
        ),
        "在 WebUI 配置 → 实验性 → 外接 Agent 里找到「工程能力（DSH Worker）」。开启前先确认本机能执行 "
        "dsh --version，并在 ~/.dsh/profiles/acp/cordis.patch.yml 配好可用模型与凭据；worker 用的是 "
        "dsh --profile acp，和 Desktop 的 profile 不共享模型配置。接着把 worker.enabled 打开：主人私聊直接可用，"
        "其他聊天要加进 worker.allow_users / allow_groups。worker.workspace 必须是已存在的绝对路径，决定它能读写哪些文件。"
        "每个任务独立会话，成功后保留 30 分钟（worker.session_ttl_seconds），同一件事的追问传 continue_from；"
        "过期或失效会报「会话已过期」而不是静默新开。进程重启会给原聊天补一条中断说明，不重放任务。"
        "需要绕过模型判断时发 /work <内容>；带文件的消息会自动附一条只读提示，但不会强制派单。",
    ),
    "help:group-reply": (
        (("群聊", "群消息", "group chat", "グループ"), ("不回复", "不回", "禁用", "暂停", "no reply", "返信しない")),
        AISearchSource(
            title="MaiBot · 群聊静默处理",
            url="https://github.com/Mai-with-u/MaiBot/blob/5553542622d1a8d96a9ab73484ce3530dca202d4/src/maisaka/reasoning_engine.py#L1127",
        ),
        "MaiBot can keep receiving group messages even when the effective group reply frequency is 0. "
        "In this case it consumes messages and maintains history without entering Planner. In WebUI, open the "
        "actual group conversation settings and check its effective reply frequency before changing adapter rules. "
        "Adapter filtering is a separate stage and can prevent messages reaching the bot at all. If the frequency "
        "is above 0, reproduce once and correlate the group message with Planner and Replyer requests. A recorded "
        "timeout or provider error on a request establishes a model failure; an absent request alone does not.",
    ),
}


def match_help_references(query: str) -> List[Dict[str, str]]:
    normalized_query = query.casefold()
    return [
        {"source_id": source_id, "title": source.title, "url": source.url, "content": content}
        for source_id, (groups, source, content) in _REFERENCES.items()
        if all(any(term in normalized_query for term in group) for group in groups)
    ]


def get_help_reference(source_id: str) -> AISearchSource | None:
    reference = _REFERENCES.get(source_id)
    return reference[1] if reference is not None else None
