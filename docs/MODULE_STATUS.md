# 模块状态

> 只用于维护；正常 PROCESS 不读取本文件。

## 已实现并有自动测试

| 模块 | 当前状态 |
|---|---|
| core | 运行目录、基础类型、显式错误、分布式快速视频指纹 |
| storage | JSON 原子写入、跨进程短锁、原子 mutate、陈旧锁恢复 |
| tasks | 路径无关 task_id、搬盘恢复、artifact / event / unresolved 原子更新 |
| workflow | input → transcript → visual → delivery → done，阶段推进原子化 |
| media | FFmpeg/ffprobe 探测、抽音频、切片、变速、按时间抽帧 |
| transcripts | SRT → 统一 Transcript、基础时间轴校验、限制段数读取 |
| asr | Provider、capability、role profile、运行配置、默认并发护栏 |
| asr/context | 课程上下文持久化；支持本次调用叠加临时词/语言/文本 |
| asr/catalog | 按需模型候选目录：速度、质量、硬件、优缺点、基准、集成状态；默认紧凑返回 |
| application | 已拆成 task / transcript / delivery / health 操作；service.py 仅薄门面 |
| recovery | media/transcript/review/delivery 中断后的已有产物可自动收口/接管 |
| review cache | 缓存键包含 Provider + 实际上下文；缓存命中与首次返回结构一致 |
| health | 不加载模型的启动体检：FFmpeg/ffprobe、ASR role/provider 配置 |
| visuals/discovery | 有上限 interval overview 候选采样 |
| visuals/cleanup | 策略注册、unresolved、同状态已确认干净源帧替换 |
| visuals/alignment | 基础图片锚点校验 |
| delivery | 缺文件、缺图、孤图、越界引用、多余顶层文件检查 |
| adapters/mcp | MCP v2 stdio Server + 薄 facade |
| CI | Python 3.11/3.13：compile、pytest、安装 MCP v2、Server 构建冒烟 |

## 仍未完成 / 尚未真实验证

| 项目 | 状态 |
|---|---|
| FunASR / Qwen Provider | 代码已实现；尚未在用户真实 Windows + GPU + 实际模型目录完成独立集成验证 |
| MCP 客户端 | Server 构建已测；尚未在实际 OpenCode / DSH / Codex 逐个连接验证 |
| visuals/discovery | 尚未实现正式场景变化 / 稳定态识别 |
| visuals/cleanup | 多帧真实像素重建、移动覆盖追踪、安全裁剪尚未正式实现 |
| visuals/alignment | 尚未实现内容级语义对位 |
| transcript verification | 尚未实现新的源段覆盖 / 更正对账协议 |
| lifecycle | 已实现任务空间统计 + 保守清理计划（只读/dry-run）；真正删除、归档与 MCP 暴露均未实现 |
| task schema migration | 当前会明确拒绝未知 schema；真正的版本迁移器尚未需要/实现 |
| Windows 实机并发 | 跨进程 JSON 锁逻辑有自动测试；仍需真实 Windows 多客户端验证 |

## 明确不做

- VideoNote-MCP 兼容层或运行依赖
- generate_note / 自动总结型笔记
- 通用 LLM Provider
- 评论 / 弹幕
- 平台扫码登录
- GPT 图像 AI
- 大而全视频平台下载

后续只根据本表“未完成”项推进，不重复实现已验证能力。
