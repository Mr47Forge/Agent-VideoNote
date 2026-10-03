# agent_videonote/workflow

工作流状态与运行规则的唯一包内实现。

- `stages.py`：阶段枚举与机械推进顺序。
- `context.py`：按当前阶段生成有界 `task_context`。
- `rules/`：随 Python wheel 一起安装的 core + 单阶段规则胶囊。
- `engine.py`：只负责持久化阶段推进，不判断 ASR/视觉质量。

运行时不依赖仓库根目录 Markdown，也不要求某个 Agent 宿主识别 `AGENTS.md` 或 Skill。换会话、换 Agent、换客户端时，以持久化 task 状态和 MCP `task_context` 为准。
