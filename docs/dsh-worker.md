# 外接工程能力（DSH Worker）

麦麦负责说话和记忆，DSH 负责干活。本文是这条链路的实现方案与维护契约。

## 结论

`dsh_task` 是一个后台工具：Planner 把一件需要动电脑的活派给 DSH（ACP 会话），调用立刻返回任务 id，
DSH 在自己的工作目录里跑完，结论作为一条内部任务送回原聊天并唤醒 Planner，由麦麦用自己的口吻转述。

它和现有 `subagent` 是同一个形态（派发即返回、后台运行、结论回送、`status`/`stop` 可查），
区别只在执行器：`subagent` 是麦麦自己的模型循环，`dsh_task` 是一个真实 DSH 进程。

**DSH 没有人格，只有工作目录。** 所有面向用户的话都由麦麦说，DSH 的正文只作为素材。
每个任务默认开一个新会话，避免上一件事的结论污染下一件事；**成功的任务会把会话保留 `session_ttl_seconds`（默认 30 分钟）**，同一件事的追问用 `continue_from` 复用，过期自动关闭。

## WebUI 入口

配置 → 实验性 → 外接 Agent → **工程能力（DSH Worker）**。字段说明就是 WebUI 上的标签和提示；
WebUI 答疑里问「怎么配置 dsh worker / 怎么让麦麦用电脑」也会命中这里的步骤摘要。

## 非目标

- 不换掉麦麦的 Planner（`agent.planner_enabled` 那条路继续冻结，见"维护契约"）。
- 不把 DSH 的工具逐个注入 Planner。弱 Planner 拿强工具只会把错误链拉长。
- 不在麦麦里重建 DSH 的沙箱、审批、后台 job、skill、CUA。
- 不新增消息注入通道：回送只用 `enqueue_internal_task`。

## 结构

```
IM 消息
  └─ maisaka Planner（麦麦，唯一说话的人）
       ├─ 闲聊/记忆/表情：原生链路，不碰 worker
       └─ dsh_task(brief, screen=False)        ← 需要动电脑时
            ├─ 立即返回 {task_id, status:"running"}，Planner 继续聊
            └─ WorkerPool
                 ├─ backend=cli      → dsh --profile acp      （文件/代码/搜索/skill/插件）
                 └─ backend=desktop  → dsh Desktop + CUA 桥接  （屏幕操作，仅主人私聊）
                      └─ 结束时：内部任务回送原聊天 → 唤醒 Planner → 麦麦转述
```

### 组件

| 模块 | 职责 |
| --- | --- |
| `src/agent/worker/session.py` | 一个聊天对应一个 DSH 会话：ACP 连接、prompt、正文收集；不挂 MCP |
| `src/agent/worker/pool.py` | 每个任务独立会话；成功的会话按 TTL 保留给追问，限制并发与停机 |
| `src/agent/worker/tasks.py` | 任务记录、状态机、超时与取消，形态对齐 `maisaka/subagent_tasks.py` |
| `src/agent/worker/provider.py` | `dsh_task` / `dsh_status` / `dsh_stop` 三个工具 |
| `src/agent/worker/delivery.py` | 把结论包装成内部任务并回送，措辞模板走 `load_prompt` |

### 工具契约

```jsonc
dsh_task {
  "brief":         "要做什么，含目标、验收标准、不能做的事",   // 必填
  "screen":        false,          // true 时走 desktop 后端（屏幕操作），默认 false
  "continue_from": "dsh-s1"        // 同一件事的追问传上一个会话句柄，30 分钟内有效
}
→ { "task_id": "dsh-2", "status": "running", "backend": "cli", "session": "dsh-s1" }

dsh_status { "task_id": "" }   // 空表示列最近任务和保留中的会话
dsh_stop   { "task_id": "dsh-1" }   // 取消并等回送；不存在或已结束直接报错
```

`brief` 由 Planner 写，不由用户消息直接截断。工具描述规定：任务要写成可验收的一句话目标 +
必要的上下文 + 明确边界；不得把整段聊天历史塞进去。

## 交接契约

DSH 的正文是素材，不是回复。回送措辞在 `prompts/*/instructions/agent/dsh_worker_result.prompt`，
核心约束是：不复述过程、不列步骤、不贴原文、失败说人话。`delivery.py` 只负责填充：

```
[后台任务 <task_id> 结束：<status>，后端 <backend>，用时 <n>s]
任务摘要：<brief 前 200 字>
结果：
<正文，超过 8000 字截断>
```

`status` 取值：`done` / `failed` / `timeout` / `cancelled`。失败时正文为空会把错误原因写进"结果"，
保证麦麦至少能说清卡在哪。

## 能力不足时

`files_read_text` 只解析 TXT/Markdown/CSV/JSON。PDF、Office、压缩包、扫描件都会返回一条可执行的错误文案，要求改用 `dsh_task` 提取或转换，而不是停在「读不了」。附件提示也会把本地路径直接给 Planner，后台不必再靠文件名搜索。

## 路由

**不做分类器。** 路由就是工具可见性 + 工具描述：

1. `dsh_task` 只对白名单聊天可见（默认关闭，配置开启）。群里默认看不到这个工具。
2. 工具描述里写清边界：要读本地文件 / 要改代码 / 要多步搜索或跑命令 → 派给 worker；
   一句话能答、只需要记忆和常识 → 自己答。
3. 显式命令 `/work <内容>`：绕过模型判断，直接在内部任务里要求调用 `dsh_task`；权限与工具白名单一致。
4. 附件提示属于后置项，等观测到稳定漏派再加。

先跑模型判断，只有观测到稳定误判时才考虑加确定性闸门。加闸门的成本远高于改一遍工具描述。

## 安全边界

- **工具可见性**：`worker.allow_users` / `worker.allow_groups`（`platform:id`），与 `agent.allow_*` 独立，
  避免"开了传话就等于开了电脑"。
- **CUA**：只有 `screen=True` 且聊天在 `worker.screen_allow_users` 里，才走 desktop 后端；默认空。
  Desktop 侧仍受 DSH 自己的审批与沙箱约束，麦麦不重复实现。
- **工作目录**：`worker.workspace` 必须是已存在的绝对路径，启动时校验，不在连接时创建；
  填 `~` 或相对路径直接报错，不做展开兜底。
- **不挂 MCP 工具**：worker 会话不接 `agent_talk`，从结构上保证后台不能直接对 IM 说话。

## 失败与恢复

| 情况 | 处理 |
| --- | --- |
| 启动程序/握手失败 | 不重试，任务标 `failed`，错误原文交给麦麦说明 |
| 单轮超时（默认 900s） | 取消会话并关闭连接，标 `timeout` |
| `stopReason != end_turn` | 标 `failed`，保留已收到的正文，不重放，会话不保留 |
| 追问时句柄过期/失效/跨聊天 | 直接报错「重新派发一个任务即可」，不静默新开会话 |
| 进程崩溃/连接失效 | 丢弃会话，标 `failed`，下次派发重建 |
| `dsh_stop` | 取消并标 `cancelled`，不重试 |
| 停机 | 取消在途任务、标 `cancelled`，不回送（避免关停时再排 Planner 回合） |
| 进程重启 | 启动时读取 `data/agent/worker/state.json`，把遗留的 running 任务向原聊天补一条中断说明；不重放 |

**不自动重发。** 执行结果未知的任务重放会造成重复的外部副作用。

## 可观测性

- 失败与异常走 `agent.worker.pool` 的日志，`dsh_status` 可回看终态、用时和错误原文。
- 在途任务写到 `data/agent/worker/state.json`（只记 running）；任务结束或关停后文件被删除，异常退出后由下次启动读取、通报并删除。
- 任务开始/结束的结构化事件、WebUI 面板留到有真实排查需求时再加，不预先建事件体系。

## 验证记录（2026-11-23）

- `pytest pytests/agent`：25 个用例通过（任务状态机、白名单、回送、会话超时、池生命周期）。
  连同 `pytests/maisaka`、`pytests/core`、`pytests/common` 合计 429 项通过；`ruff` 干净。
- 真实 DSH `0.2.2-rc.5`：`initialize` + `session/new`（空 `mcpServers`）+ `session/close` 通过；
  单轮 prompt 返回 `no API key for provider route "deepseek-official"`，说明协议链路与错误透传正常，
  缺的只是 `acp` profile 的模型凭据（见下）。

## 部署前置

worker 用的是 `dsh --profile acp`。这个 profile 与 Desktop 的 profile **不共享模型和凭据**，默认走
`deepseek-official` 的 `deepseek-v4-flash`，所以两边要分别配置：

1. `dsh` CLI 必须能在麦麦进程的 `PATH` 里执行（或把 `[agent].acp_command` 写成绝对路径）。
   只装 Desktop 时，CLI 位于 app 包内，可以借助 `ELECTRON_RUN_AS_NODE=1` 调用，或改用 Desktop 桥接。
2. `~/.dsh/profiles/acp/cordis.patch.yml` 要指向实际可用的 provider/model，并确保该 provider 的凭据
   对子进程可见（`[agent].acp_env` 可以补环境变量）。
3. 验证握手：派一个 `dsh_task`，若日志里出现 `no API key for provider route ...`，说明第 2 步没配好，
   不是 worker 的问题。


## 本机部署记录（2026-11-23）

| 位置 | 改动 | 作用 |
| --- | --- | --- |
| `~/.local/bin/dsh` | 包装 Desktop 内置 CLI（`ELECTRON_RUN_AS_NODE=1`） | 让麦麦进程能用 `dsh --profile acp` |
| `~/.dsh/profiles/acp/cordis.patch.yml` | provider 指向 `apikl`（`APIKL_API_KEY`），模型 `deepseek-v4.1-flash` | ACP 会话有可用模型 |
| `host/model_catalog.toml` | 供应商与模型改指 apikl，`deepseek-v4-flash` → `deepseek-v4.1-flash` | 麦麦自己的对话模型可用 |
| `config/bot_config.toml` | `agent.connection=dsh`、`acp_env.APIKL_API_KEY`、`agent.worker.enabled=true`、`workspace=/Users/rick/code`、会话保留 1800 秒、`capabilities.files=true` | 打通 worker 与附件 |
| `config/model_config.toml` | `model_task_config.planner` → `deepseek-v4-pro-nonthink` | flash 在任务转述上会偷懒，换 pro 后稳定 |

回滚：把上表各项改回原值并重启 Bot；`~/.local/bin/dsh` 可直接删除。

## 端到端自测（2026-11-23）

真实链路：WebUI 内部聊天 → Planner → `dsh_task` → `dsh --profile acp` → 结果回送 → 麦麦回复。

| 能力 | 结果 |
| --- | --- |
| 读本机文件 | ✅ 读 README 并总结；读 `plugins/` 列出插件与用途 |
| 联网搜索/调研 | ✅ 三条当日新闻，链接逐条核验 HTTP 200，并写入 `/Users/rick/code/ai-news-2026-11-23.md` |
| 写插件/改文件 | ✅ 参考 `hello_world_plugin` 生成插件骨架，`py_compile` 通过 |
| 回复人格 | ✅ 麦麦用自己的短句转述，没有照抄 DSH 正文 |
| 任务隔离 | ✅ 每个任务独立 DSH 会话，上一件事的结论不会污染下一件 |
| 追问复用 | ✅ 「接着刚才那个项目看 plugins」时 Planner 自动传 `continue_from=dsh-s1`，DSH 在同一个会话里回答；直连验证第二问只答「中文」也依赖第一问的上下文 |
| `/work` 显式派单 | ✅ 日志出现 `dsh_work_command:...` 内部任务并立刻触发 Planner，Planner 随后调用 `dsh_task`；不依赖模型自己判断 |
| 重启恢复 | ✅ 停机后写入一条遗留 running 记录再启动，日志出现 `dsh_worker_interrupted:...`，麦麦回复「任务没跑完 / 刚恢复就断了」，状态文件读后即删 |
| 附件提示 | ✅ WebUI 上传 `note.txt`（暗号 731），Planner 上下文出现「附件提示」，模型自己选 `tool_search` → `files_read_text` 读出 731；提示只进上下文，不进聊天记录 |
| PDF 附件 | ✅ 上传文本型 PDF（暗号 BLUE-731）：提示标成「需 `dsh_task` 提取」并给出 blob 路径，Planner 派单，worker 用 pypdf 提取并核对，48 秒后麦麦回复「BLUE-731」 |

已知限制：

- **链接可能被回复器省略**：最终回复由 replyer 生成，它只看得到 Planner 的 `chat_anlyze`（现已在里面带 URL），
  但收着「回复尽量简短」的人格约束，仍可能只说「文件在 …」而不贴 URL。要强制贴链接得改 replyer 提示词，
  属于人格层调优，不在 worker 范围内。
- **CUA 未联调**：`screen=true` 的代码路径就绪，但 Desktop 桥（`dsh-maibot-bridge`）尚未安装。
- **每次任务新开会话**：跨任务的追问连续性留到 P2；当前靠工作目录里的文件和 skill 延续。

## 阶段

| 阶段 | 内容 | 状态 |
| --- | --- | --- |
| P1 | `dsh_task` + cli 后端 + 白名单 + 回送 + 三个工具 + 超时/取消 | 已完成（2026-11-23） |
| P2 | 任务会话保留（TTL + `continue_from`） | 已完成（2026-11-23） |
| P2b | `/work` 显式派单 | 已完成（2026-11-23） |
| P2c | 重启恢复（中断说明） | 已完成（2026-11-23） |
| P2d | 附件自动提示 | 已完成（2026-11-23） |
| P3 | desktop 后端联调 + CUA（仅 `screen_allow_users`） | 代码路径已就绪，未联调 |
| P4 | skill 回流：`dsh_skills` 只读列表 + 记忆回写 | 未开始 |

## 改动清单

1. `src/agent/config.py`：`WorkerConfig` 嵌套在 `[agent.worker]`，含开关、白名单、并发、超时、工作目录。
2. `src/agent/acp.py`：`mcp_port=None` 时不再强制外部 Agent 声明 HTTP MCP；`open_session` 的 `mount`
   可为 `None`（发送空 `mcpServers`）。现有调用方默认行为不变。
3. `src/agent/worker/`：`tasks.py`（状态机）、`session.py`（纯文本 ACP 会话）、`pool.py`（按聊天复用与并发）、
   `delivery.py`（内部任务回送）、`provider.py`（三个工具）。
4. `src/maisaka/runtime.py`：注册 `DshWorkerToolProvider()`；`src/runtime.py` 在关闭聊天循环前调用
   `worker_pool.close()`，避免子进程泄漏。
5. 配置模板：`config/` 不入库，由 `Config()` 在实例初始化时生成；本次只改模型并提升
   `CONFIG_VERSION` 到 `8.16.38`，旧配置在下次加载时自动补齐 `[agent.worker]`。
6. `prompts/{zh-CN,en-US,ja-JP}/main/agent/dsh_worker_task.prompt`（派单说明）与
   `.../instructions/agent/dsh_worker_result.prompt`（回送措辞），以及各自 `.meta.toml`。
7. `pytests/agent/test_worker_{tasks,delivery,session,pool,provider}.py`：22 个用例。
8. 本文档；`docs/agent-connections.md` 加一节指向这里。

## 维护契约

- **一个 ACP 客户端**：worker 只用 `src/agent/acp.py`，不复制协议实现；改协议只改一处。
- **一个回送通道**：只用 `enqueue_internal_task`。新增第二条注入路径视为设计错误。
- **worker 不说话**：worker 会话不挂任何会发言的 MCP 工具；这条由测试保证。
- **一条废弃路径**：`agent.planner_enabled`（整条聊天流换脑）冻结，不再修功能，只保留兼容；
  新需求一律走 worker。文档和配置说明里标注"实验/冻结"。
- **提示词三语同步**：改 `dsh_worker.prompt` 必须同时改 en/ja，与现有 `i18n.md` 规则一致。
- **不写兜底**：握手失败、路径不存在、会话缺失都直接报错并暴露给 `dsh_status`，不静默重试或降级。
- 任务状态机改动必须同时更新 `pytests/agent/test_worker_tasks.py`；行为变化写进本文件而非 changelog 之外的新文档。
- `state.json` 只允许记录 running 任务：正常结束必须清掉，否则下次启动会误报中断。

## 默认值（PM 确认项）

| 配置 | 默认 | 含义 |
| --- | --- | --- |
| `worker.enabled` | `false` | 默认关闭，显式开启才给工具 |
| `worker.allow_groups` | 空 | 群里默认没有工程能力 |
| `worker.allow_users` | 空 | 空表示只在主人私聊可用，具体 owner 判定复用现有 `is_owner_chat` |
| `worker.max_concurrent` | `2` | 同时跑的任务数，超出的排队 |
| `worker.timeout` | `900` | 单任务超时秒数 |
| `worker.workspace` | `data/agent/worker/workspace` | 默认不碰用户主目录 |
| `worker.screen_allow_users` | 空 | CUA 只对列出的主人开放 |
