"""外接 ACP Agent 连接配置。"""

from typing import Dict, List, Literal

from src.config.config_base import ConfigBase, Field


class WorkerConfig(ConfigBase):
    """DSH Worker：把读文件、改代码、搜索等需要动电脑的任务交给本机 dsh，结果回到当前聊天由麦麦转述。

    开启前先确认本机能执行 dsh --version，并在 ~/.dsh/profiles/acp 配好模型与凭据；worker 用的是
    dsh --profile acp，与 Desktop 配置不共享。工作目录必须是已存在的绝对路径。详见 docs/dsh-worker.md。
    """

    __ui_label__ = "工程能力（DSH Worker）"

    enabled: bool = Field(default=False, json_schema_extra={
        "label": {"zh_CN": "启用 DSH Worker"}, "x-widget": "switch",
    })
    """启用后 Planner 可以把读文件、改代码、搜索、屏幕操作等任务派给本机 dsh 执行；关闭时不暴露任何 worker 工具。"""

    allow_users: List[str] = Field(default_factory=list, json_schema_extra={"label": {"zh_CN": "允许派发任务的私聊用户"}})
    """格式为 platform:user_id，例如 qq:123456。与 agent 白名单相互独立，避免开了传话就等于开了电脑。
    群聊成员无法单独区分，请使用 allow_groups；两个白名单均为空时只有主人私聊可以用。"""

    allow_groups: List[str] = Field(default_factory=list, json_schema_extra={"label": {"zh_CN": "允许派发任务的群聊"}})
    """格式为 platform:group_id，例如 qq:123456；默认空，群聊不获得电脑能力。"""

    screen_allow_users: List[str] = Field(default_factory=list, json_schema_extra={"label": {"zh_CN": "允许屏幕操作的用户"}})
    """格式为 platform:user_id。填写后才允许把 screen=true 的任务交给 dsh Desktop；默认空表示全部禁止。
    屏幕操作不可回滚，只应对自己开放的私聊配置。"""

    max_concurrent: int = Field(default=2, ge=1, le=8, json_schema_extra={"label": {"zh_CN": "并发任务上限"}})
    """同时运行的 worker 任务数，超出的任务排队；调大前先确认机器能承受。"""

    timeout: float = Field(default=900, gt=0, json_schema_extra={"label": {"zh_CN": "单任务超时（秒）"}})
    """超时后取消该任务所在的 DSH 会话并标记超时，不自动重跑。"""

    session_ttl_seconds: float = Field(default=1800, gt=0, json_schema_extra={
        "label": {"zh_CN": "会话保留（秒）"}, "advanced": True,
    })
    """任务结束后保留 DSH 会话的秒数；期间同一件事的追问用 continue_from 复用上下文，超时自动关闭。"""

    max_sessions: int = Field(default=4, ge=1, le=8, json_schema_extra={"label": {"zh_CN": "保留会话上限"}, "advanced": True})
    """同时保留的 DSH 会话数量；超出时关闭最早过期的那个。"""

    workspace: str = Field(default="", json_schema_extra={"label": {"zh_CN": "工作目录"}})
    """必须是已存在的绝对路径，例如 /Users/me/code；留空使用 data/agent/worker/workspace。
    填相对路径或 ~ 会直接报错，不在连接时创建目录。"""


class AgentConfig(ConfigBase):
    __ui_parent__ = "experimental"
    __ui_label__ = "外接 Agent"

    enabled: bool = Field(default=False, json_schema_extra={"label": {"zh_CN": "启用 Agent连接"}})
    """启用与普通聊天并行的外接 Agent 接口，通过 ACP 连接 dsh 等外部程序。"""

    allow_users: List[str] = Field(default_factory=list, json_schema_extra={"label": {"zh_CN": "允许指挥 Agent 的私聊用户"}})
    """私聊白名单，格式为 platform:user_id，例如 qq:123456。群聊无法按成员区分，请使用 allow_groups。
    两个白名单均为空时不限制；填写任意一项后仅放行命中的聊天。"""

    allow_groups: List[str] = Field(default_factory=list, json_schema_extra={"label": {"zh_CN": "允许指挥 Agent 的群聊"}})
    """群聊白名单，格式为 platform:group_id，例如 qq:123456。放行群内所有成员。
    两个白名单均为空时不限制；填写任意一项后仅放行命中的聊天，空白项不会解除限制。"""

    planner_enabled: bool = Field(default=False, json_schema_extra={
        "label": {"zh_CN": "启用外接 Planner（实验）"}, "x-widget": "switch",
    })
    """实验性外接 Planner 总开关，默认关闭。开启后仅对下方名单中的聊天流生效，无需启用独立 Agent 连接；关闭时保留名单。"""

    planner_sessions: List[str] = Field(default_factory=list, json_schema_extra={
        "label": {"zh_CN": "实验：外接 Planner 聊天流"}, "advanced": True,
    })
    """填写真实聊天流 session_id，开启外接 Planner 总开关后，仅这些聊天的主 Planner 使用 ACP；空列表不启用任何聊天流。
    复用下方连接配置，每个聊天流使用持久会话并增量同步上下文；重启恢复，清空聊天后重置。
    工具由原聊天运行时执行。无需启用独立 Agent 队列。
    连接失败直接报错，不回退本体 Planner；外部 Agent 自带工具仍受其自身配置控制。
    """

    connection: Literal["dsh", "dsh_desktop", "custom"] = Field(default="dsh", json_schema_extra={
        "label": {"zh_CN": "连接方式"}, "x-widget": "select",
        "options": ["dsh", "dsh_desktop", "custom"], "x-option-labels": {"dsh": "dsh CLI", "dsh_desktop": "dsh Desktop", "custom": "自定义 ACP"},
    })
    """dsh CLI 自动使用 --profile acp；dsh Desktop 连接正在运行的桌面应用，在界面中显示同一会话；自定义用于其他 ACP 程序。模型与凭据使用外部 Agent 自身配置。"""

    desktop_manifest: str = Field(default="", json_schema_extra={"label": {"zh_CN": "Desktop 桥接文件"}, "advanced": True})
    """dsh Desktop 模式使用，留空读取 ~/.dsh/maibot-desktop.json。先在 Desktop 安装 dsh-maibot-bridge 插件；不启动第二个 dsh 进程，不关闭 Desktop 应用。"""

    acp_command: str = Field(default="dsh", json_schema_extra={"label": {"zh_CN": "ACP 启动程序"}})
    """外部 Agent 可执行程序或绝对路径，不是整段 shell 命令；Windows 可填写 dsh.cmd。"""

    acp_args: List[str] = Field(default_factory=list, json_schema_extra={
        "label": {"zh_CN": "自定义启动参数"}, "advanced": True,
    })
    """仅自定义 ACP 使用，逐项填写参数；{mcp_port} 替换为本次工具服务端口，可用于 SSH -R 反向转发。dsh 预设忽略此项并自动生成 --profile acp。"""

    acp_cwd: str = Field(default="", json_schema_extra={"label": {"zh_CN": "ACP 主机工作目录"}})
    """麦麦所在主机上启动 ACP 程序（或 ssh）的工作目录，留空使用 data/agent/workspace。同一会话恢复时保持不变。"""

    acp_remote_cwd: str = Field(default="", json_schema_extra={
        "label": {"zh_CN": "ACP 远程会话工作目录"}, "advanced": True,
    })
    """远程自定义 ACP 或经 SSH 隧道连接 Desktop 时填写远端已存在的绝对路径，原样传给外部会话，不在本机创建或展开。留空使用本机工作目录；远程工具回连需配置 SSH 反向转发，详见 docs/agent-connections.md。"""

    mcp_port: int = Field(default=0, ge=0, le=65535, json_schema_extra={
        "label": {"zh_CN": "Agent 工具回连端口"}, "advanced": True,
    })
    """默认 0 自动分配本机回环端口；Desktop SSH 隧道可设固定端口并自行反向转发。同一端口只能用于一个连接；多聊天外接 Planner 应保留 0 并使用 {mcp_port}。"""

    acp_env: Dict[str, str] = Field(default_factory=dict, json_schema_extra={"label": {"zh_CN": "ACP 环境变量"}, "advanced": True})
    """追加或覆盖外部进程环境变量，例如 DSH_HOME；模型凭据建议保存在 dsh 自身配置中。"""

    acp_model: str = Field(default="", json_schema_extra={"label": {"zh_CN": "ACP 模型选项"}, "advanced": True})
    """留空使用外部 Agent 自身模型配置；填写时必须是其 model 配置选项公布的值，不使用本体 planner 回退。"""

    acp_timeout: float = Field(default=60, gt=0, json_schema_extra={"label": {"zh_CN": "ACP 连接与关停超时（秒）"}, "advanced": True})
    """握手、会话恢复和取消确认的等待时间，不限制任务执行时长。"""

    worker: WorkerConfig = Field(default_factory=WorkerConfig)
    """DSH Worker 配置，复用上面的连接设置但不要求启用独立 Agent 连接。"""
