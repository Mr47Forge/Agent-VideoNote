# Agent-VideoNote 架构约束

## 1. 项目定位

Agent-VideoNote 是一个**独立实现**的轻量视频处理运行层。

目标链路：

```text
本地视频 / 字幕
      ↓
媒体探测与切片
      ↓
主 ASR
      ↓
局部复核
      ↓
视觉候选与清理
      ↓
Agent 按阶段工作流处理
      ↓
最终转写 + 画面
```

本项目不是 VideoNote-MCP 的精简版、fork 或二次封装。

## 2. 强制模块边界

```text
adapters/          外部入口（MCP 等），只做参数转换
      ↓
application/       用例编排，不实现底层算法
      ↓
┌──────────┬──────────┬──────────┬──────────┐
tasks/     media/      asr/       visuals/
任务状态    媒体处理     语音识别    画面处理
└──────────┴──────────┴──────────┴──────────┘
      ↓
storage/            持久化实现
      ↓
core/               最小共享类型、配置、错误
```

`workflow/` 是规则和阶段定义，不直接承担 FFmpeg、ASR、图片算法或文件数据库实现。

`delivery/` 只负责最终交付结构和校验，不负责生成内容。

## 3. 依赖方向

允许：

- adapters → application
- application → tasks / media / asr / visuals / workflow / delivery
- 业务模块 → core
- tasks / workflow → storage 接口

禁止：

- ASR 直接修改任务状态文件
- FFmpeg 模块直接推进工作流
- MCP 工具内部直接写算法
- 视觉模块调用 ASR
- 工作流文档包含可执行算法实现
- 某个任务目录中的临时代码反向成为正式依赖
- 模块互相循环 import

## 4. “一坨代码”防线

任何新增功能必须先回答：

1. 它属于哪个模块？
2. 它是否能在不知道 MCP 存在的情况下独立测试？
3. 它是否把任务状态、媒体处理、模型推理混在了一个文件？
4. 它是否因为某一个视频的特殊情况而修改通用代码？
5. 能否通过参数或策略扩展，而不是复制一个新脚本？

如果一个文件同时负责两类以上核心职责，应拆分。

## 5. 模块化不是“文件多”

模块必须有清晰输入输出。

例如主 ASR：

```text
输入：音频路径 + 课程上下文
输出：标准 Transcript
```

它不应该知道：

- MCP 客户端是谁
- 最终 Markdown 在哪里
- 当前工作流状态
- 图片有多少张
- 用户是否正在处理 M3

## 6. 独立实现要求

正常安装和运行 Agent-VideoNote 时：

- 不需要安装 `videonote`
- 不 import `videonote_mcp`
- 不读取 VideoNote-MCP 的数据库
- 不依赖 VideoNote-MCP 的目录结构
- 不复制其任务 ID、缓存或配置结构作为兼容前提

若迁移历史数据，应通过独立的 `migration/` 工具完成，迁移工具不得成为正常运行依赖。
