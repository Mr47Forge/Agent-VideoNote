# 模块状态

> 用途：明确哪些模块已经有可执行实现，哪些只是接口，避免后续 Agent 凭印象判断。

## 已有第一版实现

| 模块 | 当前能力 |
|---|---|
| core | 运行目录、基础类型、错误类型 |
| storage | JSON 原子写入、任务状态文件、通用 JSON artifact |
| tasks | 稳定 task_id、创建/恢复、artifact、事件、unresolved |
| workflow | input → transcript → visual → delivery → done 的持久阶段推进 |
| media | FFmpeg/ffprobe 探测、抽音频、切片、变速、按时间抽帧 |
| transcripts | 统一 Transcript 数据结构、SRT 解析、时间轴校验 |
| asr | Provider 协议、能力声明、注册表、角色 Profile、课程上下文 |
| application | prepare、SRT 入轨、primary 转写、局部 review、视觉阶段完成、交付收口 |
| visuals/cleanup | 可复用策略注册表；现有策略无法处理时返回 unresolved |
| visuals/alignment | 基础图片锚点校验 |
| delivery | 缺文件、缺图、孤图、越界引用、多余顶层文件检查 |
| adapters/mcp | 与具体 MCP SDK 无关的薄工具门面 |
| tests | 任务续跑、工作流、ASR 能力、SRT、交付、cleanup 基础测试 |
| selfcheck | 不依赖外部模型/FFmpeg 的基础自检入口 |

## 只有接口/框架，尚未实现具体算法

| 模块 | 未完成内容 |
|---|---|
| asr/providers | 没有接任何具体识别模型 |
| visuals/discovery | 已定义策略接口与数据结构；没有稳定画面发现算法 |
| visuals/cleanup | 已有策略框架；没有正式去广告/去水印策略实现 |
| visuals/alignment | 只有基础锚点校验；没有语义自动对位算法 |
| adapters/mcp | 尚未绑定具体 MCP SDK Server |
| delivery / transcript | 尚未重新实现旧 Gate 那类完整“源段覆盖对账” |

## 刻意暂不实现

- VideoNote-MCP 兼容层
- 历史数据库直接读取
- generate_note / 自动总结笔记
- 通用 LLM Provider
- 评论弹幕
- 平台扫码登录
- GPT 图像 AI
- 大而全视频平台下载

## 下一阶段进入条件

具体第三方 ASR Provider、MCP SDK、视觉依赖在加入前，先完成 THIRD_PARTY.md 对应许可证核验。

任何新实现必须遵守 AGENTS.md 和 docs/ARCHITECTURE.md。
