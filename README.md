# Agent-VideoNote

独立、模块化的多 Agent 视频转写与图文处理运行层。

> **Agent 注意：正常 PROCESS 不要把本 README 当启动上下文。**
> 能识别 `AGENTS.md` 的宿主只用它完成启动；真正跨 Codex / DSH / OpenCode 等 MCP 客户端的运行规则由 `task_context` 返回，不依赖宿主读取仓库内 Markdown。

核心原则：

- 不依赖、不复制 VideoNote-MCP
- 媒体 / Transcript / ASR / 视觉 / 任务 / 工作流 / 协议分层
- ASR 使用可插拔 Provider，工作流不绑定模型
- 已完成状态跨会话恢复，不重复执行
- 普通任务不现场制造正式脚本
- 转写默认只返回摘要，全文按段读取
- GPT 图像 AI / 付费生成式修图不进入默认流程

运行中的真实任务状态以 MCP `task` / `health`、`task_context` 和持久化 artifact 为准；`docs/MODULE_STATUS.md` 只作为维护导航。架构维护见 `docs/ARCHITECTURE.md`；第三方许可证见 `THIRD_PARTY.md`。

## 运行入口

```text
health
  ↓
prepare(source) / task(task_id)
  ↓
context_key
  ↓
新会话或 key 变化时 task_context(task_id)
  ↓
core_rules + 当前 stage_rules
  ↓
调用对应 MCP 能力
```

`task_context` 的工作流规则随 Python 包一起安装，因此运行不依赖源码仓库根目录存在。

## 目标链路

```text
本地视频 / 时间码字幕
        ↓
媒体探测
        ↓
统一 Transcript
   ↙              ↘
字幕解析       可替换 ASR Provider
                   ↓
             可选局部 review
        ↓
画面发现 / 清理 / 对位
        ↓
最终转写 + 画面
```

## 主要模块

```text
core / tasks / storage / media / transcripts
asr / visuals / workflow / delivery / adapters
```

这是新项目，不提供 VideoNote-MCP 兼容层。
