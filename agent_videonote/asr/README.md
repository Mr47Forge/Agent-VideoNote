# asr

语音识别能力模块。

## 核心原则

**系统认识能力，不认识固定模型。**

内部结构：

- `providers/`：不同识别引擎/模型的独立实现
- `profiles/`：把任务角色映射到具体 Provider
- `context/`：热词、课程上下文
- 未来 `types.py`：统一 Transcript / Segment / Capability 数据结构

## 角色

默认只定义能力角色：

- `primary`：产生主时间轴
- `review`：局部独立复核，可关闭
- `context`：提供识别上下文

角色不是模型名称。

例如某一台机器可以配置：

```text
primary = provider_a
review  = provider_b
```

另一台也可以：

```text
primary = provider_b
review  = disabled
```

或者同一个 Provider 同时承担 primary 和 review。

## Provider 能力声明

每个 Provider 应声明自己支持哪些能力，例如：

- 长音频 / 短音频
- 分段时间戳
- 逐字时间戳
- 热词
- 自由上下文
- 指定语言
- GPU / CPU
- 批处理
- 常驻模型实例
- 本地 / 远程

application 根据“任务需要的能力”选择 Provider，不根据品牌名写分支。

任何 Provider 私有返回格式都必须在 ASR 模块内部转换成统一结果，不能泄漏到 workflow、MCP 或 delivery。
