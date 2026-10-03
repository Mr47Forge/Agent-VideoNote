# Agent-VideoNote 架构约束

## 1. 项目定位

Agent-VideoNote 是一个**独立实现**的轻量视频处理运行层。

目标链路：

```text
本地视频 / 字幕
      ↓
媒体探测与切片
      ↓
ASR 能力选择
      ↓
主转写 / 可选复核
      ↓
视觉候选与清理
      ↓
Agent 按阶段工作流处理
      ↓
最终转写 + 画面
```

本项目不是 VideoNote-MCP 的精简版、fork 或二次封装。

## 2. 强制模块边界

```text
adapters/          外部入口（MCP 等），只做参数转换
      ↓
application/       用例编排，不实现底层算法
      ↓
┌──────────┬──────────┬──────────┬──────────┐
tasks/     media/      asr/       visuals/
任务状态    媒体处理     识别能力     画面处理
└──────────┴──────────┴──────────┴──────────┘
      ↓
storage/            持久化实现
      ↓
core/               最小共享类型、配置、错误
```

`agent_videonote/workflow/` 保存阶段定义与随 Python 包分发的运行规则，不直接承担 FFmpeg、ASR、图片算法或文件数据库实现。

`delivery/` 只负责最终交付结构和校验，不负责生成内容。

## 3. 依赖方向

允许：

- adapters → application
- application → tasks / media / asr / visuals / workflow / delivery
- 业务模块 → core
- tasks / workflow → storage 接口

禁止：

- ASR Provider 直接修改任务状态文件
- FFmpeg 模块直接推进工作流
- MCP 工具内部直接写算法
- 视觉模块调用 ASR
- 工作流文档包含可执行算法实现
- 某个任务目录中的临时代码反向成为正式依赖
- 模块互相循环 import
- application / workflow / adapters 根据具体模型品牌写业务分支

## 4. ASR 是能力插件，不是固定模型

ASR 模块分为三层：

```text
profiles/      角色配置：primary / review 等
    ↓
providers/     具体实现：本地模型、远程服务等
    ↓
统一结果类型   Transcript / Segment / WordTiming
```

工作流只知道：

- 是否需要主时间轴
- 是否需要局部独立复核
- 当前任务需要哪些能力

它不应该知道当前背后是哪个品牌、型号或框架。

Provider 必须声明能力，例如：

- timestamp.segment
- timestamp.word
- hotwords
- free_context
- long_audio
- batch
- local
- gpu
- persistent_instance

application 按能力与配置调用 Provider。

## 5. “一坨代码”防线

任何新增功能必须先回答：

1. 它属于哪个模块？
2. 它是否能在不知道 MCP 存在的情况下独立测试？
3. 它是否把任务状态、媒体处理、模型推理混在了一个文件？
4. 它是否因为某一个视频的特殊情况而修改通用代码？
5. 能否通过参数、Provider 或策略扩展，而不是复制一个新脚本？

如果一个文件同时负责两类以上核心职责，应拆分。

## 6. 模块化不是“文件多”

模块必须有清晰输入输出。

例如 ASR：

```text
输入：音频路径 + 可选上下文 + 所需能力
输出：统一 Transcript
```

它不应该知道：

- MCP 客户端是谁
- 最终 Markdown 在哪里
- 当前工作流状态
- 图片有多少张
- 用户正在处理哪个课程
- 某个模型名是不是“默认答案”

## 7. 独立实现要求

正常安装和运行 Agent-VideoNote 时：

- 不需要安装 `videonote`
- 不 import `videonote_mcp`
- 不读取 VideoNote-MCP 的数据库
- 不依赖 VideoNote-MCP 的目录结构
- 不复制其任务 ID、缓存或配置结构作为兼容前提

若迁移历史数据，应通过独立的 `migration/` 工具完成，迁移工具不得成为正常运行依赖。

## 8. 事实源层级

为了避免 Skill / workflow / 文档 / 状态文件互相复制，按下面的层级判断“谁说了算”：

1. **任务运行状态**：`tasks/<task-id>/state.json` 是阶段、artifact 索引、unresolved 和事件的机器真源，只通过 `TaskService` / `WorkflowEngine` 修改。
2. **产物内容**：具体 transcript、visual discovery、cleanup、delivery 等 artifact 文件是其内容真源；`state.json` 只保存索引和摘要，不复制正文。
3. **Agent 运行路由**：`AGENTS.md` 只是宿主可选启动提示；跨 Agent 真正统一的运行入口是 MCP `task_context`。阶段规则随 Python 包位于 `agent_videonote/workflow/rules/`，由 `context_key` 标识版本；Agent 不需要读取源码仓库文件。
4. **运行能力与环境**：ASR / Cleanup Provider 是否可用，以运行配置、Registry 和 `health` 的实际结果为准。
5. **维护文档**：`docs/**`、模块 README、`THIRD_PARTY.md` 用于解释架构、许可证和历史决策，不得反向覆盖机器状态或被普通 PROCESS 当作运行真源。

`task()` 是对 `state.json` 的有界派生视图，不产生第二份状态；它返回当前阶段、`context_key`、核心 artifact 和分类计数。`task_context()` 再按这个机器状态读取包内唯一规则资源，返回 `core_rules + stage_rules`。新增运行状态字段时，优先扩展机器状态/派生摘要，不在 Markdown 中另建平行状态表。

同理，本项目不新增一个与 MCP runtime 平行的 `SKILL.md + task-*` 运行体系。Skill 宿主能力不一致，而 MCP 是 Codex / DSH / OpenCode 等客户端共同的运行边界；阶段胶囊通过 `task_context` 统一下发。
