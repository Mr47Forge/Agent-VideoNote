# 目录规范

## 源代码仓库

```text
Agent-VideoNote/
├─ agent_videonote/
│  ├─ core/
│  ├─ application/
│  ├─ tasks/
│  ├─ media/
│  ├─ asr/
│  │  ├─ primary/
│  │  ├─ review/
│  │  └─ context/
│  ├─ visuals/
│  │  ├─ discovery/
│  │  ├─ cleanup/
│  │  └─ alignment/
│  ├─ workflow/
│  ├─ delivery/
│  ├─ storage/
│  └─ adapters/
│     └─ mcp/
├─ workflow/
├─ docs/
├─ tests/
└─ THIRD_PARTY.md
```

## 运行数据

运行数据不进入源码仓库。

建议：

```text
Agent-VideoNote-Data/
├─ models/
├─ tasks/
│  └─ <task-id>/
│     ├─ state.json
│     ├─ source/
│     ├─ transcript/
│     ├─ reviews/
│     ├─ frames/
│     ├─ unresolved/
│     └─ temp/
├─ context/
└─ backups/
```

## 规则

- 一个任务的中间文件只能进入自己的任务目录。
- 禁止在项目根目录堆 `_fix1.py`、`_ad_final2.py` 之类临时脚本。
- 临时实验如果值得复用，必须经过 MAINTENANCE 收编进正式模块和测试；否则随任务生命周期清理。
- 模型目录不和源码混放。
- 历史项目迁移数据不和正常运行数据混放。
