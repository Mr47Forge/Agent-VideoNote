# 目录规范

## 源代码仓库

```text
Agent-VideoNote/
├─ agent_videonote/
│  ├─ core/
│  ├─ application/
│  ├─ tasks/
│  ├─ storage/
│  ├─ media/
│  ├─ transcripts/       # 统一时间轴文本
│  ├─ asr/
│  │  ├─ providers/      # 具体识别实现，可插拔
│  │  ├─ profiles/       # primary/review 等角色映射
│  │  └─ context/        # 课程热词与上下文
│  ├─ visuals/
│  │  ├─ discovery/
│  │  ├─ cleanup/
│  │  │  └─ strategies/
│  │  └─ alignment/
│  │  │  └─ rules/          # 随 Python 包分发，由 task_context 按阶段读取
│  ├─ delivery/
│  └─ adapters/
│     └─ mcp/
├─ workflow/
├─ docs/
├─ examples/
├─ tests/
└─ THIRD_PARTY.md
```

## 运行数据

运行数据不进入源码仓库。

```text
Agent-VideoNote-Data/
├─ models/
├─ tasks/
│  └─ <task-id>/
│     ├─ state.json
│     ├─ source/
│     │  ├─ media.json
│     │  └─ audio.wav
│     ├─ transcript/
│     │  └─ transcript.json
│     ├─ reviews/
│     ├─ frames/
│     ├─ delivery/
│     ├─ unresolved/
│     └─ temp/
├─ context/
│  ├─ asr-runtime.json
│  └─ courses/
└─ backups/
```

## 规则

- 一个任务的中间文件只能进入自己的任务目录。
- 禁止在项目根目录堆 `_fix1.py`、`_ad_final2.py` 一类临时脚本。
- 临时实验值得复用时，经过 MAINTENANCE 收编进正式模块和测试；否则随任务生命周期清理。
- 模型目录与源码分离。
- 历史项目迁移数据与正常运行数据分离。
- 具体模型名只能出现在 Provider 实现、运行配置、许可证登记和历史基线中。
- task_id 不依赖盘符/目录路径；源文件搬盘只更新当前 source path。
