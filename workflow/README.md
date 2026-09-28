# 工作流读取规则

正常 PROCESS 只需先读 `00-core.md`。

MCP 返回当前 `current_stage` 后，再读取**一个**对应阶段文件。不要一次加载整个 `workflow/` 目录。
