# 上下文预算规则

本文件是维护说明，**正常 PROCESS 不需要读取**。

## 目标

MCP 未启动前，Agent 的项目上下文保持在极小范围；启动后由机器状态决定只加载一个阶段胶囊，避免把架构史、许可证、模块说明和源码全量灌入上下文。

## 三类资料

### A. 运行必读

仅：

- `AGENTS.md`
- `workflow/00-core.md`
- `prepare` / `task` 返回 `workflow_file` 后，对应的一份阶段文件

阶段映射不在 prompt 中手工维护，避免工作流文件改名或新增阶段后出现第二份路由事实。

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
- `docs/REUSE_AUDIT.md`
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
health + prepare/task
  ↓
task.workflow_file
  ↓
只加载这一份阶段规则
  ↓
执行
```

如果 MCP 启动失败，只读取与错误直接相关的入口、配置和测试，不允许用“全仓扫描”作为默认排障方式。

## 静态预算

CI 对默认运行提示词执行硬预算：

- `AGENTS.md` ≤ 2,500 bytes
- `workflow/00-core.md` ≤ 2,000 bytes
- 单个阶段胶囊 ≤ 3,000 bytes
- `AGENTS + core + 最大阶段胶囊` ≤ 7,000 bytes

预算测试只约束默认运行链，不限制维护文档长度。需要更深资料时按问题局部读取，而不是把参考资料重新塞回默认上下文。

## 预算原则

- 不把 README 当运行 prompt。
- 不重复加载已经由 MCP 状态表达的信息。
- 不通过对话记忆保存任务进度。
- `task()` 只返回有界摘要；大量 artifact、events、unresolved 详情不默认展开。
- 大文本按段读取；只有当前任务确需时才打开具体 artifact。
- 文档用于维护，机器状态用于运行。
