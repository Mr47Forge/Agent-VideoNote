# adapters/mcp

MCP 薄适配层。

职责：

- 接收工具参数
- 调用 application 用例
- 返回紧凑结果

禁止：

- 在 MCP tool 函数中直接加载模型
- 在 MCP tool 函数中拼 FFmpeg 命令
- 在 MCP tool 函数中实现工作流业务判断
- 把完整长转写默认塞回 Agent 上下文
