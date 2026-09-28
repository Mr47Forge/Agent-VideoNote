# Agent-VideoNote · 最小启动规则

## PROCESS（正常跑视频）

启动时只读：
1. 本文件
2. `workflow/00-core.md`

然后立即连接/启动 MCP，并优先调用 `health`、`prepare` 或 `task` 获取真实状态。

**禁止在 MCP 启动前预读：**
- `README.md`
- `docs/**`
- 各模块 `README.md`
- 整个源码树
- `tests/**`
- 历史任务目录

拿到 `current_stage` 后，只读对应阶段规则：
- input → `workflow/10-input.md`
- transcript → `workflow/20-transcript.md`
- visual → `workflow/30-visual.md`
- delivery → `workflow/40-delivery.md`

已持久化完成的阶段不得因换会话、换 Agent 或上下文压缩而重读重做。

## MAINTENANCE（改代码）

只读本文件 + 当前要修改的模块代码/测试；需要时再按需读对应设计文档。禁止为了“先了解项目”全仓扫文档和源码。

## 红线

- 独立于 VideoNote-MCP，不复制、不恢复其运行依赖。
- MCP adapter 只做协议适配，不放 ASR/FFmpeg/视觉/工作流业务。
- 普通 PROCESS 不现场制造正式脚本；缺能力记 unresolved。
- workflow/application/task state/MCP 协议不硬编码具体 ASR 模型。
- 转写工具默认只返回摘要，全文按段读取。
- GPT 图像 AI / 付费生成式修图不进入默认流程。

其余架构、许可证、历史基线都属于**按需维护资料，不是运行上下文**。
