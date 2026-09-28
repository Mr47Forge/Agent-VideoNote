# Agent-VideoNote · Agent 工作约束

任何 Agent 在修改本仓库前先读本文件，再读与当前任务有关的模块 README。

## 项目身份

Agent-VideoNote 是**独立实现**。

不是：

- VideoNote-MCP fork
- VideoNote-MCP 精简版
- VideoNote-MCP 插件
- VideoNote-MCP 兼容层

正常运行不得依赖 VideoNote-MCP。

## 不允许做的事

1. 不复制 VideoNote-MCP 源代码进本仓库。
2. 不为了“省事”恢复对 `videonote_mcp`、其数据库、缓存、配置或任务目录的依赖。
3. 不把多个核心职责重新塞进一个大文件。
4. 不在 MCP adapter 中实现 ASR、FFmpeg、视觉处理或业务状态机。
5. 不在普通 PROCESS 中临时新建正式 Python / PowerShell / BAT 脚本。
6. 不把某一个视频的特殊参数硬编码成全局规则。
7. 不自动调用 GPT 图像 AI 或其他付费生成式修图。
8. 不因为换会话、换客户端或上下文压缩而重新执行已经持久化完成的阶段。
9. 未完成许可证核验前，不把第三方组件写成“可商用已确认”。

## 模块职责

- `core/`：共享基础类型
- `application/`：用例编排
- `tasks/`：任务状态与恢复
- `media/`：FFmpeg/ffprobe
- `asr/`：主转写、局部复核、上下文
- `visuals/`：画面发现、清理、对位
- `workflow/`：机器状态
- 根目录 `workflow/`：Agent 可读规则
- `delivery/`：交付检查
- `storage/`：持久化适配
- `adapters/`：MCP 等外部协议

## 新功能判断

新增代码前必须先确定唯一归属模块。

如果一个新需求需要同时修改多个模块，应通过清晰接口连接，而不是直接互相 import 内部实现。

如果临时实验最终证明值得复用：

```text
任务实验
  ↓
MAINTENANCE
  ↓
正式模块
  ↓
测试
  ↓
再供 PROCESS 调用
```

不能让任务目录本身成为长期代码仓库。
