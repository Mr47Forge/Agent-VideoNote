# Agent-VideoNote

面向 OpenCode、DSH、Codex 等 Agent 的独立视频处理运行层。

**这不是 VideoNote-MCP 的精简版、fork 或兼容层。**

项目直接组合第三方上游能力和自己的任务状态、时间轴、视觉处理、工作流与交付校验，目标是长期可维护、可商业化审计、跨 Agent 可续跑。

## 当前状态

第一版模块化运行层已经落地，但还不是完整的视频生产版本。

已经具备：

- 路径无关的视频任务身份与 JSON 持久状态
- FFmpeg / ffprobe 媒体封装
- SRT → 统一 Transcript
- 可插拔 ASR Provider / capability / role profile
- 通用 FunASR AutoModel Provider
- 通用 Qwen3-ASR Provider
- 课程级术语/上下文持久化
- 主转写完成只返回摘要，正文按段读取，单次最多 200 段
- 局部 review 结果落盘并复用
- 有上限的视觉 overview 候选采样
- 视觉 cleanup 策略注册表与 unresolved 机制
- “同稳定态已确认干净源帧替换”安全清理策略
- 交付目录、缺图、孤图、越界引用、多余文件检查
- MCP v2 薄 Server
- 自检与 GitHub Actions

尚未完成的重点见 `docs/MODULE_STATUS.md`。

## 原则

- 不复制 VideoNote-MCP 源代码
- 不把 VideoNote-MCP 作为运行依赖
- 不读取其数据库、缓存或任务目录作为正常运行前提
- 第三方库和模型直接从各自上游接入
- 工作流只依赖“能力角色”，不依赖具体模型名称
- 已完成阶段不会因为换会话、换 Agent 或搬动源文件而自动失效
- 普通 PROCESS 不现场制造正式脚本
- GPT 图像 AI / 付费生成式修图不进入默认工作流

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
Agent 分阶段处理
        ↓
最终转写 + 画面
```

## 模块结构

```text
agent_videonote/
├─ core/           最小共享类型、配置、错误
├─ application/    用例编排
├─ tasks/          任务状态与续跑
├─ storage/        持久化适配
├─ media/          FFmpeg / ffprobe 封装
├─ transcripts/    与来源无关的统一时间轴文本
├─ asr/
│  ├─ providers/   可插拔识别实现
│  ├─ profiles/    primary/review 等角色映射
│  └─ context/     课程热词和上下文
├─ visuals/
│  ├─ discovery/   候选画面、稳定状态
│  ├─ cleanup/     广告/水印清理策略
│  └─ alignment/   图片与正文对位
├─ workflow/       工作流机器状态
├─ delivery/       最终交付机械校验
└─ adapters/
   └─ mcp/         MCP 薄适配层
```

Agent 可读规则单独放在根目录 `workflow/`，不和 Python 实现混在一起。

## ASR 设计原则

系统固定的是能力角色，不是模型：

- `primary`：生成主时间轴
- `review`：对疑难片段提供独立第二读法，可选
- `context`：识别上下文

具体 Provider 由运行配置决定。一个 Provider 可以承担多个角色，也可以只承担一个角色。替换模型不应修改 workflow、task state 或 MCP 工具协议。

历史使用过的具体模型只作为候选实现，不构成架构绑定。

## 架构红线

1. MCP 层不能直接实现 ASR、FFmpeg 或视觉算法。
2. ASR Provider 不直接修改任务状态。
3. Transcript 不属于 ASR；字幕和 ASR 都只是 Transcript 来源。
4. 媒体模块不知道 workflow 和 Agent。
5. 视觉模块不负责修改转写文字。
6. 普通任务不能因为遇到新广告就在任务目录新造正式脚本。
7. 运行数据、模型、中间帧不进入源码仓库。
8. 正常运行不得要求安装 VideoNote-MCP。
9. workflow / application / task state / MCP 协议不得硬编码具体模型名。
10. 全文不得作为“转写完成”的默认工具返回值。

详细设计见：

- `AGENTS.md`
- `docs/ARCHITECTURE.md`
- `docs/ASR_DESIGN.md`
- `docs/MODULE_STATUS.md`
- `docs/DECISIONS.md`
- `THIRD_PARTY.md`

## 第一阶段明确不做

- 原项目自动总结型笔记
- 通用 LLM Provider 管理
- GPT API 管理
- 评论 / 弹幕
- Playwright 登录
- 大而全的平台下载
- Web UI
- 旧 VideoNote-MCP 兼容层

## 商业化准备

第三方代码和模型分别登记许可证、制品来源和分发方式，见 `THIRD_PARTY.md`。
