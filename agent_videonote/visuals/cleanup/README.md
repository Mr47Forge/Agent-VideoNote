# visuals/cleanup

广告、水印、遮挡清理策略库。

## 运行原则

- **只有一个 Python 环境**：所有 Cleanup Provider 都使用当前 Agent-VideoNote 的 `sys.executable`。
- 不创建 `VSR/.venv`、`ProPainter/.venv` 或任何嵌套虚拟环境。
- 第三方源码放在运行数据目录的 `third_party/`，不塞进 Agent-VideoNote Git 仓库。
- 模型放在共享模型目录 `models/visual-cleanup/`。
- VSR 只做稀疏源码安装：只取 LaMa/STTN/ProPainter 推理所需代码，不安装 GUI、PaddleOCR、DirectML 等无关依赖。
- Big-LaMa、STTN、ProPainter 权重统一从固定 VSR revision 获取；分块下载后校验 Git blob SHA，合并完成即删除临时分块，不保留重复权重。
- ProPainter 直接复用 VSR 已集成的 ProPainter 推理代码和同一套权重，不再额外 clone 第二份 ProPainter 仓库。
- 优先同状态干净帧和源视频真实像素。
- 生成像素 Provider 必须显式指定 `provider` 和 `mask_path`，不会根据 OCR 文字自动删除内容。

## 一键安装

先启动在 **Agent-VideoNote 自己现有的 venv** 中，然后调用：

```text
visual_setup(apply=false)
```

查看计划。

确认后：

```text
visual_setup(apply=true)
```

它会：

1. 在当前 venv 补齐最小依赖；
2. 复用当前 Torch，不新建环境；
3. 如果缺 torchvision，只安装与当前 Torch 对应的版本；
4. 稀疏安装固定 revision 的 VSR 推理源码；
5. 下载并校验 Big-LaMa、STTN、ProPainter 所需权重；
6. 写入 `context/visual-runtime.json`；
7. 要求重启 MCP，让 Provider 从持久化配置重新加载。

如果当前 Python 是系统全局 Python，安装器会拒绝写入，避免污染系统。

## 已接 Provider

| ID | 实际来源 | 用途 |
|---|---|---|
| `source-frame-replacement` | Agent-VideoNote | 同状态真实干净帧替换 |
| `opencv` | OpenCV | 小面积静态区域修复 |
| `vsr-lama` | VSR / Big-LaMa | 单张、近静态画面修复 |
| `vsr-sttn` | VSR / STTN | 多帧时序修复 |
| `propainter` | VSR 内集成的 ProPainter | 复杂多帧修复 |

## 安全边界

这些 Provider 只负责：

> 已经给出明确 mask 后，如何修复 mask 区域。

它们不负责决定“哪些文字应该删除”。

因此默认禁止：

- OCR 检测到文字后直接清除；
- 自动把聊天气泡当广告；
- 自动删除课件文字；
- 无 mask 直接运行生成式修复。

聊天正文、课程正文、图表文字必须由上层安全判断保护。
