# visuals/cleanup

广告、水印、遮挡清理策略库。

核心原则：

- 固定的是策略接口，不是单一去广告算法。
- 优先同状态干净帧和源视频真实像素。
- 生成像素的 Provider 必须显式指定 `provider` 和 `mask_path`，不会根据 OCR 文字自动删除内容。
- 不允许普通任务因为遇到新广告就新建一个 Python 脚本。
- 新广告类型无法由现有策略安全处理时，输出“未解决案例”，进入维护阶段统一研究。
- 第三方大模型保持外部运行，不把整套上游仓库复制进 Agent-VideoNote。

## 已接 Provider

| ID | 来源 | 用途 | 默认行为 |
|---|---|---|---|
| `source-frame-replacement` | 本项目 | 同状态真实干净帧替换 | 第一优先级，不生成像素 |
| `opencv` | OpenCV | 小面积静态区域修复 | 可选依赖；必须显式 mask |
| `vsr-lama` | VSR / Big-LaMa | 单张/静态画面修复 | 外部 VSR 环境；不自动下载 |
| `vsr-sttn` | VSR / STTN | 多帧时序修复 | 外部 VSR 环境；至少 3 帧；不自动下载 |
| `propainter` | 官方 ProPainter | 复杂多帧修复 | 外部仓库调用；缺权重直接 unavailable，禁止触发上游自动下载 |

## 可选配置

OpenCV：

```text
pip install -e ".[visual-cleanup]"
```

VSR：

```text
AGENT_VIDEONOTE_VSR_ROOT=<VSR 仓库目录>
AGENT_VIDEONOTE_VSR_PYTHON=<VSR Python，可选>
AGENT_VIDEONOTE_VSR_LAMA_MODEL=<big-lama 权重>
AGENT_VIDEONOTE_VSR_STTN_MODEL=<STTN 权重>
```

ProPainter：

```text
AGENT_VIDEONOTE_PROPAINTER_ROOT=<ProPainter 仓库目录>
AGENT_VIDEONOTE_PROPAINTER_PYTHON=<ProPainter Python，可选>
```

ProPainter 只有在 `weights/raft-things.pth`、`weights/recurrent_flow_completion.pth`
和 `weights/ProPainter.pth` 已经存在时才会执行。Agent-VideoNote 不替它自动下载。

这些 Provider 只负责“给定明确 mask 后如何修复”。“哪里应该删除”仍由上层安全判断负责。
聊天正文、课件文字、截图中的真实文字不能因为通用文字检测自动变成 mask。
