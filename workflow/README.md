# 工作流读取规则

正常 PROCESS 只先读 `00-core.md`。

启动 MCP 后，`prepare` / `task` 会返回当前任务的 `workflow_file`：

- 非空：只加载这一份阶段文件。
- 为空：当前没有阶段胶囊需要加载。
- 不在 Agent prompt 中重复维护 stage → 文件名映射。

阶段文件彼此独立，不把另一阶段文件设为默认前置；跨阶段事实由持久化 task / artifact 状态传递。
