# 上下文预算规则

本文件是维护说明，**正常 PROCESS 不需要读取**。

## 目标

MCP 未启动前，Agent 的项目上下文应保持在极小范围，避免把架构史、许可证、模块说明和源码全量灌入上下文。

## 三类资料

### A. 运行必读

仅：

- `AGENTS.md`
- `workflow/00-core.md`
- MCP 返回当前阶段后，对应的一个 `workflow/<stage>.md`

### B. 维护按需读

只有修改对应模块时才读：

- `docs/ARCHITECTURE.md`
- `docs/ASR_DESIGN.md`
- `docs/MODULE_STATUS.md`
- 模块 README
- 对应源码和测试

### C. 非运行资料

正常视频处理严禁预读：

- `docs/BASELINE.md`
- `docs/DECISIONS.md`
- `docs/DIRECTORY_LAYOUT.md`
- `docs/PROJECT_BOUNDARIES.md`
- `THIRD_PARTY.md`
- Git 历史
- 历史任务数据
- 全仓测试文件

这些资料只在架构追溯、发布、许可证审计或专项维护时读取。

## 冷启动顺序

```text
AGENTS.md
  ↓
workflow/00-core.md
  ↓
启动/连接 MCP
  ↓
health / prepare / task
  ↓
current_stage
  ↓
只加载当前阶段规则
  ↓
执行
```

如果 MCP 启动失败，只读取与错误直接相关的入口、配置和测试，不允许用“全仓扫描”作为默认排障方式。

## 预算原则

- 不把 README 当运行 prompt。
- 不重复加载已经由 MCP 状态表达的信息。
- 不通过对话记忆保存任务进度。
- 工具返回保持紧凑；大文本必须分页/分段。
- 文档用于维护，机器状态用于运行。
