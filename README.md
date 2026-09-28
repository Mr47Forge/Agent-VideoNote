# Agent-VideoNote

面向 OpenCode、DSH、Codex 等 Agent 的独立视频处理运行层。

**这不是 VideoNote-MCP 的精简版、fork 或兼容层。**

项目目标是直接组合第三方上游能力和我们自己的工作流、任务状态、视觉处理与交付校验，形成一套可长期维护、可商业化审计、跨 Agent 可复用的轻量系统。

## 当前阶段

目前只搭建**模块化骨架与边界**，还没有把旧项目代码迁入。

原则：

- 不复制 VideoNote-MCP 源代码
- 不把 VideoNote-MCP 作为运行依赖
- 不读取其数据库、缓存或任务目录作为正常运行前提
- 第三方库和模型未来直接从各自上游接入
- **工作流只依赖“能力角色”，不依赖具体模型名称**
- 先做最小链路，再按真实需求增加能力

## 目标链路

```text
本地视频 / 时间码字幕
        ↓
媒体探测与切片
        ↓
转写能力（可替换 Provider）
        ↓
可选的独立复核能力
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
├─ media/          FFmpeg / ffprobe 封装
├─ asr/
│  ├─ providers/   可插拔识别实现
│  ├─ profiles/    角色到 Provider 的配置
│  └─ context/     热词和课程上下文
├─ visuals/
│  ├─ discovery/   候选画面、稳定状态
│  ├─ cleanup/     广告/水印清理策略
│  └─ alignment/   图片与正文语义对位
├─ workflow/       工作流状态的机器表示
├─ delivery/       最终交付机械校验
├─ storage/        持久化适配
└─ adapters/
   └─ mcp/         MCP 薄适配层
```

Agent 可读规则单独放在根目录 `workflow/`，不和 Python 实现混在一起。

## ASR 设计原则

系统固定的是能力角色，不是模型：

- `primary`：生成主时间轴
- `review`：对疑难片段提供独立第二读法，可选
- `context`：向支持的 Provider 提供热词/课程上下文

具体 Provider 由配置决定。一个 Provider 可以承担多个角色，也可以只承担一个角色。未来替换本地模型、其他本地引擎或远程服务时，不应修改工作流、MCP 协议或任务状态结构。

历史上使用过 Fun-ASR-Nano-2512 和 Qwen3-ASR-1.7B，只是**历史验证过的候选实现**，不是项目架构的一部分。

## 架构红线

1. MCP 层不能直接实现 ASR、FFmpeg 或视觉算法。
2. ASR Provider 不直接修改任务状态文件。
3. 媒体模块不知道工作流和 Agent 的存在。
4. 视觉模块不负责改转写文字。
5. 普通视频任务不能因为遇到新情况就在任务目录新造正式脚本。
6. 已完成状态不能因为换会话或换 Agent 自动失效。
7. 运行数据、模型、任务中间产物不进入源码仓库。
8. GPT 图像 AI / 付费生成式修图不属于默认工作流。
9. 正常运行不得要求安装 VideoNote-MCP。
10. 工作流和应用层不得硬编码具体 ASR 模型名。

详细约束：

- `docs/ARCHITECTURE.md`
- `docs/ASR_DESIGN.md`
- `docs/PROJECT_BOUNDARIES.md`
- `docs/DIRECTORY_LAYOUT.md`
- `THIRD_PARTY.md`

## 第一阶段明确不做

- 原项目自动笔记生成
- 通用 LLM Provider 管理
- GPT API 管理
- 评论 / 弹幕
- Playwright 登录
- 大而全的平台下载
- Web UI
- 说话人分离
- 多格式笔记导出
- 旧 VideoNote-MCP 兼容层

## 商业化准备

第三方代码和模型会分别登记许可证与分发方式，见 `THIRD_PARTY.md`。

当前仓库不从 VideoNote-MCP 复制实现，避免未来再次做一次“脱钩”。
