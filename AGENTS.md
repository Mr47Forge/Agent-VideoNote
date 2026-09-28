# Agent-VideoNote · Agent 工作约束

任何 Agent 修改本仓库前先读本文件，再读当前模块 README。

## 项目身份

Agent-VideoNote 是**独立实现**。

不是 VideoNote-MCP 的 fork、精简版、插件或兼容层。正常运行不得依赖 VideoNote-MCP。

## 不允许做的事

1. 不复制 VideoNote-MCP 源代码。
2. 不恢复对其数据库、缓存、配置或任务目录的运行依赖。
3. 不把多个核心职责重新塞进一个大 server.py / manager.py / utils.py。
4. 不在 MCP adapter 中实现 ASR、FFmpeg、视觉算法或工作流业务。
5. 不在普通 PROCESS 中临时新建正式 Python / PowerShell / BAT 脚本。
6. 不把某个视频的特殊参数硬编码成全局规则。
7. 不自动调用 GPT 图像 AI 或付费生成式修图。
8. 不因为换会话、换客户端、源文件搬盘或上下文压缩而重新执行已经持久化完成的阶段。
9. 未完成许可证核验前，不把第三方组件写成“商用已确认”。
10. 不把具体 ASR 模型名硬编码进 workflow、application、task state 或 MCP 对外协议。
11. “转写完成”只返回摘要；全文必须通过有上限的分段读取工具获取。
12. Provider 私有返回字段不能泄漏到 workflow、delivery 或 MCP 对外协议。

## 模块职责

- `core/`：共享基础类型、配置、错误
- `application/`：用例编排
- `tasks/`：任务状态与恢复
- `storage/`：持久化
- `media/`：FFmpeg/ffprobe
- `transcripts/`：统一时间轴文本，不关心来源
- `asr/`：Provider、能力声明、角色配置、识别上下文
- `visuals/`：候选画面、清理策略、对位
- `workflow/`：机器状态
- 根目录 `workflow/`：Agent 可读规则
- `delivery/`：交付检查
- `adapters/`：MCP 等外部协议

## ASR 约束

workflow 只允许依赖 `primary` / `review` 等角色，不得依赖 Nano、Qwen、Whisper、SenseVoice 等具体实现名称。

具体模型属于 Provider 配置。替换模型时，正常情况下只应修改 Provider 或配置。

## PROCESS 与 MAINTENANCE

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

不能让任务目录本身成为长期代码仓库。现有策略无法安全解决时，应记录 unresolved，而不是在 PROCESS 中无限试错。
