# Agent-VideoNote · 最小启动规则

## PROCESS（正常跑视频）

启动时只读本文件，然后立即连接/启动 Agent-VideoNote MCP。

运行顺序：

1. 调用 `health`。
2. 新任务调用 `prepare`；已有 task_id 调用 `task`。
3. 新会话、首次进入任务，或 `context_key` 发生变化时，调用一次 `task_context`。
4. 只按 `task_context` 返回的 `core_rules + stage_rules` 执行当前阶段；不要自行扫描仓库寻找工作流规则。

已持久化完成的阶段不得因换会话、换 Agent 或上下文压缩而重读重做。任务进度以 MCP 机器状态为准，不以聊天记忆或维护文档为准。

**MCP 启动前禁止预读：**

- `README.md`
- `docs/**`
- 各模块 `README.md`
- 整个源码树
- `tests/**`
- 历史任务目录

## MAINTENANCE（改代码）

只读本文件 + 当前要修改的模块代码/测试；只有确实需要架构、许可证或历史决策时，才按需读对应文档。禁止为了“先了解项目”全仓扫文档和源码。

维护红线：

- MCP adapter 只做协议适配，不放 ASR / FFmpeg / 视觉 / 工作流业务。
- workflow / application / task state / MCP 协议不硬编码具体 ASR 模型。
- 运行数据、模型和用户任务状态不进入源码仓库。
- 已经稳定并有测试的模块，不为了统一目录或风格做无收益重写。

`AGENTS.md` 只是对能识别它的宿主提供启动提示；真正跨 Agent 的运行规则由 MCP `task_context` 提供。
