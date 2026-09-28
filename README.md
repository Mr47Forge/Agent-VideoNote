# Agent-VideoNote

面向 OpenCode、DSH、Codex 等 Agent 的轻量视频转写与图文整理运行层。

这个项目不是 VideoNote-MCP 的继续堆叠版，而是为实际批量课程处理重新做的最小实现：只保留高准确率转写、局部复核、媒体切片/取帧、可续跑任务状态，以及按阶段加载的工作流。

## 目标

- 第一遍准确率优先，不追求“最快出字”
- Fun-ASR-Nano-2512 作为主转写，支持课程热词
- Qwen3-ASR-1.7B 只做有争议片段的局部复核
- FFmpeg / ffprobe 负责确定性的媒体处理
- 每个视频有独立任务目录和持久化状态，新会话可继续
- 工作流按当前阶段加载，避免每轮把整份长规则塞进上下文
- 不允许普通视频任务现场新造 Python / PowerShell 脚本
- 去广告只使用本地、低成本、可复用方法；不依赖 GPT 图像 AI 或付费生成式修图

## 第一版明确不包含

- 原版 `generate_note` / `batch_generate_notes`
- LLM Provider / OpenAI API 管理
- 原版自动写笔记
- 评论、弹幕抓取
- Playwright / 二维码登录
- Whisper 主路线
- Web UI
- 大而全的平台适配
- 自动调用昂贵图像生成/修复模型

需要这些能力时，先证明它对当前工作流是必要的，再单独加入。

## 架构

```text
OpenCode / DSH / Codex
        │
        ▼
   Agent-VideoNote MCP
        │
        ├─ 任务状态 / 续跑
        ├─ FFmpeg / ffprobe
        ├─ Fun-ASR-Nano-2512 + 课程热词
        ├─ Qwen3-ASR 局部复核
        ├─ 音频切片 / 视频取帧
        └─ 紧凑结果读取
        │
        ▼
按阶段加载 workflow/*.md
```

## 工作流文档

- `workflow/00-core.md`：所有任务都必须遵守的少量硬边界
- `workflow/10-transcribe.md`：转写与课程热词
- `workflow/20-verify.md`：疑难句复核与停止条件
- `workflow/30-visual.md`：取图、广告/水印处理边界
- `workflow/40-package.md`：最终转写与图片交付

Agent 在一个会话中先读取 `00-core.md`，之后只读取当前任务阶段对应的文件。不要为每个视频反复全文加载全部规则。

## 运行数据

默认保存到：

```text
%LOCALAPPDATA%\Agent-VideoNote\data
```

可通过环境变量修改：

- `AGENT_VIDEONOTE_DATA_DIR`
- `AGENT_VIDEONOTE_MODEL_DIR`

现有模型可以继续复用，不要求重新下载；把 `AGENT_VIDEONOTE_MODEL_DIR` 指向已有模型目录即可。

## 当前状态

这是与原 VideoNote-MCP 解耦后的第一版骨架。优先把本地课程视频的核心链路跑稳，再决定是否增加网址下载等外围能力。
