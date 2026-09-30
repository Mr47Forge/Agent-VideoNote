# 成熟能力复用审计

> 维护用文档，不属于 PROCESS 启动必读材料。  
> 首次审计：2026-09-30。

目标：减少重复造轮子；只有业务状态、安全约束、工作流语义确实属于 Agent-VideoNote 时才继续自研。

## 已接入 / 已决定复用

| 模块 | 上游 | 方式 | 状态 |
|---|---|---|---|
| ASR primary/review | FunASR / Qwen ASR | Provider | 已接 |
| 小区域图像修复 | OpenCV | 可选 Provider | 已接 |
| 静态图像补全 | VSR / Big-LaMa | 外部 Provider | 已接适配层 |
| 时序视频补全 | VSR / STTN | 外部 Provider | 已接适配层 |
| 复杂视频补全 | sczhou/ProPainter | 外部 Provider / subprocess | 已接适配层 |
| 固定 Logo 处理思路 | propainter-delogo | 参考其窗口化、分镜感知设计 | 不复制整仓 |

所有生成式 Cleanup Provider 都要求显式 Provider + 明确 mask；默认不使用 OCR 自动删文字。

## 下一阶段优先复用

### Visual Alignment

优先：

1. **RapidOCR**：离线中文/英文 OCR，Apache-2.0，中文文档完整。
2. **RapidFuzz**：OCR 文本与时间附近 transcript 的快速模糊匹配，MIT。

推荐流程：

```text
候选图
→ RapidOCR 提取文字
→ 时间戳限制匹配范围
→ RapidFuzz 与附近 transcript 匹配
→ 得到正文插入锚点
```

不要自己写 OCR，也不要自己实现 Levenshtein/模糊匹配算法。

如 RapidOCR 在实际聊天截图上效果不够，再评估 PaddleOCR；不要一开始同时维护两套。

## 已有模块：暂不为了换库而返工

### Visual Discovery

现有自研内容包括：

- scene/content change；
- 局部 tile change；
- perceptual hash；
- zoom / pan 对齐；
- 跨时间去重。

成熟替代候选：

- PySceneDetect：场景切换；
- OpenCV：特征/图像对齐；
- ImageHash：pHash/dHash；
- scikit-image：SSIM。

但当前 Discovery 已经过真实课程库回归并稳定，**现在不重写**。

只有未来出现新的结构性缺陷，才优先评估上述库能否替代对应局部算法，而不是再次扩写自研通用视觉算法。

### SRT

当前只需要简单可靠 SRT，现有解析器保持。

若后续需要：

- ASS / SSA；
- 多字幕轨；
- 样式；
- 更复杂时间轴编辑；

优先接 `pysubs2`，不继续扩写自定义字幕格式解析器。

### 文件锁

当前 `JsonTaskStore` 自研短锁已经经过跨进程测试。

若以后出现 Windows/Linux 锁语义问题，再评估：

- portalocker；
- filelock。

现在不为“用库而用库”重构稳定锁。

### FFmpeg

继续直接调用 ffmpeg/ffprobe 并保留薄 MediaBackend。

不需要为了包装而引入 ffmpeg-python；当前 subprocess 封装就是合适边界。

## 应继续自研

这些是 Agent-VideoNote 自己的业务价值，不应交给通用第三方库替代：

- Workflow 状态机；
- Task / Artifact；
- 断点恢复；
- Provider Registry；
- 模型生命周期；
- MCP 薄层；
- 运行上下文预算；
- clean / resolved / unresolved；
- source provenance；
- 安全回滚；
- course context；
- delivery gate。

## 后续开发规则

每个新算法模块开始前按顺序判断：

1. GitHub / PyPI 是否已有成熟项目？
2. 是否能做薄 Provider / Adapter？
3. 许可证与模型权重是否允许当前用途？
4. 是否会增加不必要的大依赖？
5. 只有以上均不适合时，才进入自研。

不得先写一套复杂算法，再事后搜索有没有成熟实现。
