# 第三方依赖登记

> 本文件用于未来许可证与商业化审计。  
> 初次核验日期：2026-09-28；视觉 Cleanup 补充核验：2026-09-30。  
> 这里记录的是**当前上游公开许可证状态**，不等于最终商业发布法律审查。正式打包前仍需按“实际版本 + 实际模型制品 + 实际 FFmpeg 构建”再次核验。

## 原则

Agent-VideoNote 不以 VideoNote-MCP 为代码依赖，也不复制其源代码。

ASR 架构不绑定任何具体模型。视觉 Cleanup 同样采用 Provider / Adapter：成熟第三方算法优先作为外部后端调用，不把大仓库整体复制进主项目。

| 组件 | 候选用途 | 当前上游许可证状态 | 商业化注意事项 | 当前结论 |
|---|---|---|---|---|
| FFmpeg / ffprobe | 媒体处理 | 主体为 LGPL-2.1+；若构建启用 GPL 部件则整体按 GPL-2.0+ | **必须检查实际二进制构建参数** | 可作为候选，打包方式待定 |
| FunASR toolkit | ASR Provider 框架 | MIT | 模型权重需单独看模型卡 | 代码层初步可用 |
| FunAudioLLM/Fun-ASR-Nano-2512 | 本地 ASR 模型候选 | 官方 Hugging Face 模型卡当前标 Apache-2.0 | 发布前固定具体 revision 并重新核验模型卡 | 模型候选初步可用 |
| QwenLM/Qwen3-ASR 代码 | 本地 ASR Provider 框架候选 | Apache-2.0 | 分发修改版需保留相应许可证/NOTICE义务 | 代码层初步可用 |
| Qwen/Qwen3-ASR-1.7B | 本地 ASR 模型候选 | 官方 Hugging Face 模型卡当前标 Apache-2.0 | 发布前固定具体 revision 并重新核验 | 模型候选初步可用 |
| PyTorch | 模型运行环境 | BSD 风格三条款许可证 | 分发二进制时保留相应版权/免责声明 | 初步可用 |
| MCP Python SDK | Agent 接口 | MIT | 正式绑定版本时重新核验 | 初步可用 |
| OpenCV 4.5+ | 小面积图像修复 / 视觉基础算子 | Apache-2.0 | 若实际部署旧于 4.5，需按对应旧版 BSD-3-Clause 重新登记 | `opencv` Cleanup Provider 已适配 |
| YaoFANGUK/video-subtitle-remover (VSR) | LaMa / STTN 外部修复后端参考与运行体 | Apache-2.0 | VSR 内部各模型权重仍需分别核验；本项目不启用“检测所有文字后自动删除” | `vsr-lama` / `vsr-sttn` 外部 Provider 已适配 |
| researchmm/STTN | 视频时序补全上游 | MIT | 预训练权重来源仍需单独记录 | 通过 VSR 适配，暂不复制官方仓库 |
| sczhou/ProPainter | 视频时序补全上游 | NTU S-Lab License 1.0，**仅非商业使用** | 商业用途需另行获得许可；代码和权重都受其单独许可证约束 | 仅外部 Provider；当前非商业自用可评估 |
| QuantumWars/propainter-delogo | 固定 Logo 的窗口化、分镜感知处理参考 | MIT；其调用的 ProPainter 许可证独立 | 不能因 wrapper 是 MIT 就忽略 ProPainter 的非商业限制 | 采用“外部调用 + 窗口化思路”，不复制整仓 |
| MCG-NKU/E2FGVI | 视频补全候选 | CC BY-NC 4.0 | 非商业限制；与 ProPainter 能力重叠 | 暂不接入，避免重复维护 |

## 当前来源基线

- FunASR 官方仓库说明：toolkit 源代码为 MIT；模型权重以各模型卡为准。
- Fun-ASR-Nano-2512 官方 Hugging Face 模型卡当前显示 Apache-2.0。
- Qwen3-ASR 官方仓库 LICENSE 为 Apache-2.0；Qwen3-ASR-1.7B 官方 Hugging Face 模型卡当前显示 Apache-2.0。
- MCP Python SDK 官方仓库为 MIT。
- PyTorch 官方 LICENSE 为 BSD 风格三条款。
- FFmpeg 官方许可证说明：默认主体 LGPL-2.1+，启用 GPL 部件后构建会转为 GPL-2.0+。
- OpenCV 官方许可证说明：4.5.0 及以上为 Apache-2.0，旧版为 BSD-3-Clause。
- VSR 官方仓库当前标 Apache-2.0。
- STTN 官方仓库当前为 MIT。
- ProPainter 官方 LICENSE/README 明确为 NTU S-Lab License 1.0，非商业使用。
- propainter-delogo 自身为 MIT，但明确声明 ProPainter 和权重许可证独立。
- E2FGVI 官方仓库当前为 CC BY-NC 4.0。

## 发布前必须再次检查

1. 锁定每个第三方包的确切版本。
2. 锁定每个模型的确切仓库与 revision。
3. 记录是否把模型权重随程序一起分发，还是由用户自行下载。
4. 记录 FFmpeg 的来源、版本和构建参数。
5. 生成最终 THIRD_PARTY_NOTICES。
6. 检查依赖树中是否又引入了额外 GPL / AGPL / 自定义模型许可证。

## 禁止事项

- 不因为“开源”三个字就默认可随意商用。
- 不把代码许可证和模型权重许可证混为一谈。
- 不把历史项目依赖表直接复制到本项目。
- 不因为某模型当前效果好，就把模型名写进 workflow、task state 或 MCP 对外协议。
- 不把某个社区转换模型的许可证，自动视为官方原模型许可证。
- 不把 OCR 检测到的课程文字、聊天文字自动当作待删除 mask。
