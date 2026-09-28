# asr

语音识别模块。

内部继续拆分：

- `primary/`：主转写实现
- `review/`：局部复核实现
- `context/`：热词、课程上下文
- `types.py`：统一 Transcript / Segment 数据结构

主 ASR 和复核 ASR 必须通过统一接口向 application 暴露，外部流程不能依赖某个模型私有返回格式。
