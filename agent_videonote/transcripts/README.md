# transcripts

统一的“时间轴文本”领域层。

来源可以是：

- SRT / VTT / ASS 等可靠时间码字幕
- 任意 ASR Provider
- 未来其他可验证来源

这里的 Transcript 不属于某个 ASR 模型。

职责：

- 统一 Segment / Word / Transcript 数据结构
- 字幕解析
- 时间轴基础校验
- 后续覆盖检查所需的标准输入

禁止把模型品牌、MCP 协议或最终 Markdown 逻辑放进本模块。
