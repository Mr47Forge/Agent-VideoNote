# 上下文预算规则

本文件是维护说明，**正常 PROCESS 不需要读取**。

## 目标

不同 Agent 宿主对 `AGENTS.md` / Skill 的自动加载能力并不一致，因此运行上下文不能依赖“宿主会自己去读某个仓库文件”。

跨 Agent 的统一链路是：

```text
MCP
 ↓
health.runtime_protocol
 ↓
prepare / task
 ↓
context_key
 ↓
新会话或 key 变化时 task_context
 ↓
core_rules + 当前唯一 stage_rules
```

工作流 Markdown 随 Python 包安装在：

`agent_videonote/workflow/rules/`

因此源码仓库、当前工作目录和宿主类型都不是运行前提。

## 三类资料

### A. 运行上下文

只包含：

- MCP `task` 的有界机器状态；
- `task_context` 返回的 `core_rules`；
- 当前唯一 `stage_rules`。

`AGENTS.md` 只是能识别它的宿主的启动提示，不是跨 Agent 的运行真源。

### B. 维护按需读

只有修改对应模块时才读：

- `docs/ARCHITECTURE.md`
- `docs/ASR_DESIGN.md`
- `docs/MODULE_STATUS.md`
- 模块 README
- 对应源码和测试

### C. 非运行资料

正常视频处理严禁预读：

- `docs/BASELINE.md`
- `docs/DECISIONS.md`
- `docs/DIRECTORY_LAYOUT.md`
- `docs/PROJECT_BOUNDARIES.md`
- `docs/REUSE_AUDIT.md`
- `THIRD_PARTY.md`
- Git 历史
- 历史任务数据
- 全仓测试文件

## 静态预算

CI 对包内运行规则执行硬预算：

- `core_rules` ≤ 2,000 bytes
- 单个阶段胶囊 ≤ 3,000 bytes
- `core_rules + 最大阶段胶囊` ≤ 5,000 bytes
- `AGENTS.md` ≤ 2,500 bytes

另外 CI 必须验证构建出的 wheel 实际包含全部规则文件，防止“源码目录能跑、安装包缺规则”。

## 预算原则

- 不把 README / docs 当运行 prompt。
- 不通过对话记忆保存任务进度。
- `health()` 只增加一个很小的 `runtime_protocol`，用于无 AGENTS / 无 Skill 宿主自举。
- `task()` 只返回有界状态摘要，并显式提供 `context_tool`。
- `task_context()` 只在新会话或 `context_key` 变化后读取一次，不在每个工具调用里重复返回规则。
- 大文本按段读取；只有当前任务确需时才打开具体 artifact。
- 文档用于维护，机器状态用于运行。
