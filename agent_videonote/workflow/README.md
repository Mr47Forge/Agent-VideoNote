# agent_videonote/workflow

工作流状态的机器表示。

这里实现阶段、状态、停止条件和恢复逻辑。

人类/Agent 可读规则放在仓库根目录 `workflow/`。

两者必须分离：

- 根目录 `workflow/`：规则文本
- Python `agent_videonote/workflow/`：状态数据结构与机械校验

换会话、换 Agent、换客户端不得自动清空已完成状态。
