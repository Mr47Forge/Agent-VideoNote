# 模块维护导航

> 本文件**不是当前任务状态或运行能力的事实源**，正常 PROCESS 不读取。
> 它只告诉维护者“某类能力去哪里看、用什么验证”，避免手工状态表随代码演进而漂移。

## 运行时应该相信什么

| 问题 | 唯一优先来源 |
|---|---|
| 当前任务在哪个阶段、完成了什么 | MCP `task` / 持久化 `state.json` |
| 当前应该读哪个工作流文件 | `task.workflow_file` |
| ASR / Cleanup Provider 当前是否可用 | MCP `health` + 运行配置 / Registry |
| transcript / visual / cleanup / delivery 的实际内容 | 对应 artifact 文件 |
| 某个行为是否真的被实现并受保护 | 当前源码 + 自动测试 |
| 为什么曾这样设计 | `docs/DECISIONS.md` / Git 历史 |

不要用本文件覆盖以上任何来源。

## 维护入口

| 能力域 | 主要代码 | 主要测试 |
|---|---|---|
| task / state / artifact 索引 | `agent_videonote/tasks/`, `storage/` | `test_tasks.py`, `test_storage_concurrency.py`, `test_compact_task_summary.py` |
| workflow 阶段与路由 | `agent_videonote/workflow/`, `workflow/` | `test_workflow.py`, `test_runtime_context_contract.py` |
| media | `agent_videonote/media/` | 相关 application / recovery 测试 |
| transcript / SRT | `agent_videonote/transcripts/`, `application/transcript_ops.py` | `test_srt.py`, `test_application_srt.py`, `test_review_cache.py` |
| ASR Provider / lifecycle / setup | `agent_videonote/asr/` | `test_asr_registry.py`, `test_provider_*`, `test_asr_setup_plan.py` |
| course context | `agent_videonote/asr/context/` | `test_course_context.py` |
| visual discovery | `agent_videonote/visuals/discovery/` | `test_visual_discovery.py`, `test_visual_interval.py` |
| visual cleanup / repair | `agent_videonote/visuals/cleanup/`, `visuals/setup.py` | `test_cleanup_*`, `test_visual_cleanup_phase1.py`, `test_visual_setup.py` |
| visual alignment | `agent_videonote/visuals/alignment/` | 对应 alignment / delivery 测试 |
| delivery | `agent_videonote/delivery/`, `application/delivery_ops.py` | `test_delivery.py`, recovery 测试 |
| MCP | `agent_videonote/adapters/mcp/` | CI Server build / smoke |

## 维护判断规则

- 看到这里的路径后，只读要改模块和相邻测试，不默认扫完整仓库。
- 要判断“已经实现到什么程度”，先看代码和测试，不维护第二份逐功能完成清单。
- 真实 GPU、模型、FFmpeg、第三方运行体是否可用，必须看 `health` / 实机结果；CI 通过不能替代本机能力判断。
- 新能力优先扩展现有 Provider / application / artifact 协议；除非出现新的独立职责，不因为文件变长就创建一套新框架。
