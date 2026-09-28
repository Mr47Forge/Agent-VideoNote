# 模块状态

> 用途：明确哪些模块已经有实现，哪些仍是接口，避免后续 Agent 凭印象判断。

## 已有第一版实现

| 模块 | 当前能力 |
|---|---|
| core | 运行目录、基础类型、错误、源文件快速内容指纹 |
| storage | JSON 原子写入、任务状态、通用 artifact |
| tasks | 路径无关 task_id、搬盘恢复、artifact、事件、unresolved |
| workflow | input → transcript → visual → delivery → done 的持久阶段推进 |
| media | FFmpeg/ffprobe 探测、抽音频、切片、变速、按时间抽帧 |
| transcripts | 统一 Transcript、SRT 解析、时间轴基础校验、按段读取 |
| asr | Provider 协议、capability、注册表、role profile、运行配置 |
| asr/context | 课程级术语和上下文持久化 |
| asr/providers | 通用 FunASR AutoModel Provider、通用 Qwen3-ASR Provider；具体模型由配置决定 |
| application | prepare、SRT 入轨、primary 转写、局部 review、分段读取、交付收口 |
| visuals/discovery | 有上限的 interval overview 候选采样 |
| visuals/cleanup | 策略注册表、unresolved、已确认同状态干净源帧替换 |
| visuals/alignment | 基础图片锚点校验 |
| delivery | 缺文件、缺图、孤图、越界引用、多余顶层文件检查 |
| adapters/mcp | MCP v2 stdio Server + 薄 facade |
| tests / CI | 核心单测、Python 3.11/3.13 GitHub Actions |
| selfcheck | 不依赖模型/FFmpeg 的基础状态自检 |

## 仍未完成或只完成基础版

| 模块 | 下一步 |
|---|---|
| visuals/discovery | 场景变化/稳定态识别；当前 interval 只用于 overview，不假装自动选图 |
| visuals/cleanup | 多帧真实像素重建、移动覆盖追踪、安全裁剪等策略尚未正式实现 |
| visuals/alignment | 尚未实现内容级语义对位算法 |
| transcript verification | 尚未实现新的源段覆盖/更正对账协议 |
| Provider runtime | 两个 Provider 已实现代码，但仍需在用户真实 Windows/GPU/模型环境做集成验证 |
| MCP runtime | Server 已按 MCP v2 接入，但需在实际 OpenCode/DSH/Codex 客户端做连接验证 |
| lifecycle | 尚未实现任务 temp/frame 清理与归档策略 |

## 刻意不实现

- VideoNote-MCP 兼容层
- 历史 SQLite / note_results 直接作为运行依赖
- generate_note / 自动总结型笔记
- 通用 LLM Provider
- 评论弹幕
- 平台扫码登录
- GPT 图像 AI
- 大而全视频平台下载

## 当前验证状态

- GitHub Actions 已建立：Python 3.11 / 3.13 运行 compileall + pytest。
- 早期核心版本 CI 已通过。
- Provider、MCP Server、最新任务身份与新增测试加入后，必须以最新提交的 CI 结果为准，不能沿用旧结果。
- 真实 GPU 模型推理尚未在本仓库独立运行环境中验证。

任何新实现必须遵守 `AGENTS.md` 和 `docs/ARCHITECTURE.md`。
