# DSH Worker 上线与运维说明

> 归档日期：2026-11-23。记录「麦麦说、DSH 做」这条链路的架构、部署、验证证据和已知技术债。
> 代码事实以本分支（`perf/off-critical-path`）为准；实例配置只存在于部署机，不在仓库里。

## 1. 这条链路做什么

Planner 遇到需要动电脑的任务时调用 `dsh_task`，把自包含的 brief 交给本机 `dsh --profile acp` 执行；
结果作为内部任务回送原聊天，由麦麦用自己的口吻转述。后台没有人格，只有工作目录。

```
IM / WebUI
  └─ 麦麦 Planner（唯一说话的人）
       ├─ 闲聊、记忆、表情：原生链路
       ├─ /work <内容>：绕过模型判断，强制派单
       └─ dsh_task(brief, screen, continue_from)
            ├─ WorkerPool：每任务独立会话，成功后按 TTL 保留
            ├─ 附件：文件工具读不了的类型，提示带本地路径与处理方式
            └─ 结束：内部任务回送 → 唤醒 Planner → 麦麦转述
```

## 2. 模块

| 位置 | 职责 |
| --- | --- |
| `src/agent/worker/pool.py` | 任务调度、并发上限、会话保留（TTL + 上限）、崩溃状态落盘与启动补通报 |
| `src/agent/worker/session.py` | 纯文本 ACP 会话：握手、prompt、正文收集、超时取消；不挂 MCP |
| `src/agent/worker/tasks.py` | 任务状态机与最近任务保留 |
| `src/agent/worker/provider.py` | `dsh_task` / `dsh_status` / `dsh_stop` |
| `src/agent/worker/delivery.py` | 结果与中断说明的内部任务文本 |
| `src/agent/worker/policy.py` | 工具与 `/work` 共用的白名单判定 |
| `src/agent/worker/command.py` | `/work` 解析与派单文本 |
| `src/agent/worker/attachment.py` | 附件类型分流与本地路径汇总 |
| `src/files/extract.py` | PDF 文本层提取（pypdf、NFKC、页数上限） |
| `src/files/service.py` | `convert_to_markdown`：PDF → 带页码 Markdown 附件 |
| `src/chat/message_receive/bot.py` | `/work` 拦截、附件提示注入 |
| `src/main.py` / `src/runtime.py` | 启动恢复、关停前关闭 worker 池 |

## 3. 能力矩阵

| 能力 | 状态 | 证据 |
| --- | --- | --- |
| 读本机文件 | ✅ | 读 README 并总结 |
| 联网搜索/调研 | ✅ | 三条当日新闻 + 链接核验 200，落文件 |
| 写插件/改文件 | ✅ | 参考 hello_world 生成插件骨架，py_compile 通过 |
| PDF 文本（原生） | ✅ | `files_convert` → `files_read_text`，11 秒 |
| PDF 文本（worker 兜底） | ✅ | 48 秒，pypdf + 目视复核 |
| 追问复用 | ✅ | Planner 自动传 `continue_from`，同会话回答 |
| 重启恢复 | ✅ | 遗留 running 记录 → `dsh_worker_interrupted` 通报 |
| `/work` 显式派单 | ✅ | 日志 `dsh_work_command` → `dsh_task` |
| 附件提示 | ✅ | 类型分流 + 本地路径，模型据此选工具 |
| 扫描件 PDF | ⚠️ 未验证 | 无文本层会报错并转 worker，OCR 路径未实测 |
| Office（docx/pptx/xlsx） | ⚠️ 走 worker | 未做原生转换 |
| CUA（鼠标键盘） | ❌ 未接 | 需要 Desktop 桥 + 系统授权，等具体场景 |

## 4. 部署拓扑

| | 本机 Mac（测试服） | mini（生产） |
| --- | --- | --- |
| 实例根 | `bots/<id>/`（`config/`、`data/`） | `~/apps/maibot`（`MAIBOT_INSTANCE_DIR`） |
| 代码 | `/Users/rick/code/MaiBot`（git） | `~/code/MaiBot`（**无 git 历史的拷贝**） |
| WebUI | `127.0.0.1:8001` | `100.74.18.68:8001` |
| worker.workspace | `/Users/rick/code` | `/Users/morty/code` |
| 模型 | apikl / deepseek-v4.1-flash，Planner 用 v4-pro-nonthink | 同口径 |
| 状态 | 只用于调试 | 线上，配置改动需谨慎 |

生产与仓库的 `src/agent/worker/*`、`src/files/*`、`src/chat/message_receive/bot.py`、
`src/main.py`、`src/runtime.py`、`src/maisaka/runtime.py`、`src/agent/config.py`、`src/config/config.py`
已逐一核对 sha256 一致（2026-11-23 20:0x）。

## 5. 运维手册

```sh
# 启动 / 重启 / 停止（在实例根执行）
maibot run
maibot host restart --bot-id <id>
maibot host status
maibot host open-webui          # 一次性登录链接
```

关键配置（`config/bot_config.toml`）：

| 键 | 值 | 说明 |
| --- | --- | --- |
| `[agent] connection / acp_command` | `dsh` / `dsh` | 用 `dsh --profile acp` |
| `[agent] acp_env` | `APIKL_API_KEY` | 子进程凭据；与 Desktop 不共享 profile |
| `[agent.worker] enabled` | `true` | 关闭时不暴露 worker 工具 |
| `[agent.worker] workspace` | 绝对路径 | 决定 worker 能读写的目录 |
| `[agent.worker] session_ttl_seconds` | `1800` | 追问复用窗口 |
| `[agent.worker] timeout` | `900` | 单任务超时 |
| `[capabilities] files` | `true` | **为 false 时附件全部不可读**（本次 PDF 问题的根因） |

依赖：`pypdf` 必须装在 **uv 工具环境**，只有仓库 `.venv` 不够：

```sh
uv pip install --python "$(head -1 ~/.local/bin/maibot | sed 's/^#!//')" "pypdf>=6.0,<8"
```

排障入口：`logs/app_*.jsonl`（工具调用与错误）、`logs/maisaka_prompt/`（Planner/Replyer 实际上下文）、
`data/agent/worker/state.json`（在途任务）、`dsh_status` 工具。

回滚：`worker.enabled=false` 即撤回全部工具；删除 `~/.local/bin/dsh` 可断开 CLI；
`~/.dsh/profiles/acp/cordis.patch.yml` 恢复为空数组即回到默认 provider。

## 6. 已知技术债

**P1（影响可信度）**

1. **mini 代码是拷贝，没有 git 历史**；每次靠人工同步，已经出现一次漂移：本机 reply 侧 20:08 的改动
   尚未同步到 mini（19:53 版本）。同步后必须核对 `shasum -a 256`。
2. **任务进度仍在轮询**：Planner 会 `wait` + `dsh_status` 查进行中的任务，虽然已提示「结果会自动送回」，
   但模型习惯未根除。可考虑：派发后 10 秒内的 status 直接返回「别查」，或让 `wait` 不打断自动回送。

**P2（能力缺口）**

3. `files_convert` 每次调用都新建一份 Markdown 附件，同一 PDF 多次转换会产生多份副本；缺去重/缓存。
4. 扫描件 PDF 未实测：无文本层会正确报错，但 worker 的 OCR/视觉链路没有验证过。
5. Office 文件（docx/pptx/xlsx）仍全部交给 worker，没有原生转换。
6. worker 任务只有异常日志，没有结构化的开始/结束指标；排障依赖工具记录与 prompt 快照。

**P3（细节）**

7. `attachment.py` 在取本地路径失败时静默降级为空路径（提示仍可用，但少了关键信息）。
8. `_announce_interrupted` 固定 `sleep(3)` 等聊天就绪，属于经验值。
9. `provider.list_tools` 与 `_allowed` 重复判断 `enabled`（无害）。
10. `/work` 与 `convert_to_markdown` 只有单元测试，没有端到端用例。

## 7. 同步与归档约定

- 仓库本分支是唯一事实来源；实例配置（`config/`、`host/`、`data/`）不入库。
- 本机存在另一会话未提交的 reply 侧改动（2026-11-23 20:08），不在本次归档范围内。
- 归档提交：`f723729`…`de8d457`（7 个 worker/files 相关提交），基于 `origin/main` 之上共 10 个提交。

## 8. 复现步骤

1. `dsh --version` 可用；`~/.dsh/profiles/acp/cordis.patch.yml` 指向可用 provider。
2. 运行环境装 `pypdf`（见 §5）。
3. 实例配置：`agent.connection=dsh`、`agent.worker.enabled=true`、`capabilities.files=true`、workspace 指向实际目录。
4. 重启 Bot，主人私聊发一张文本型 PDF，问「暗号是什么」；日志应出现 `files_convert` → `files_read_text`。
5. 发一条需要动电脑的指令（如「看看 plugins 目录」），日志应出现 `dsh_task` → `dsh_worker_result`。
