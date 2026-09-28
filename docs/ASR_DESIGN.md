# ASR 可插拔设计

## 目标

ASR 层解决的是“提供识别能力”，不是“绑定某个模型”。

任何具体模型都只能作为 Provider 存在。

## 三个概念

### Provider

一个具体识别实现。

例子可以是：

- 某个本地 FunASR 模型
- 某个 Qwen ASR 模型
- Whisper 系列
- SenseVoice
- 其他本地模型
- 远程 ASR API

项目核心代码不预设这些一定存在。

### Capability

Provider 声明自己支持什么。

建议能力键：

- `transcribe.short_audio`
- `transcribe.long_audio`
- `timestamp.segment`
- `timestamp.word`
- `context.hotwords`
- `context.free_text`
- `language.explicit`
- `batch`
- `runtime.persistent_instance`
- `runtime.local`
- `runtime.gpu`

### Profile

Profile 只决定“哪个角色用哪个 Provider”。

例如：

```yaml
roles:
  primary: local_a
  review: local_b
```

也可以：

```yaml
roles:
  primary: local_a
  review: null
```

或者：

```yaml
roles:
  primary: local_a
  review: local_a
```

## 统一输出

Provider 私有结果必须转成统一结构，再离开 ASR 模块。

建议核心结构：

```text
Transcript
├─ text
├─ segments[]
│  ├─ start
│  ├─ end
│  └─ text
├─ words[]          可选
├─ language         可选
├─ provider_id
└─ metadata
```

workflow、delivery、MCP adapter 不得读取某个 Provider 的私有字段。

## 选择规则

第一版不做复杂自动路由。

优先级：

1. 用户/机器配置的 profile；
2. 校验 Provider 是否满足当前角色必需 capability；
3. 不满足则明确报错。

禁止“配置 A 不行就偷偷换 B”。

未来如果确实需要自动路由，再单独设计策略模块。

## 模型生命周期

Provider 自己负责：

- 模型加载
- 模型实例复用
- 显存释放
- 并发限制

application 不应该知道模型如何加载。

特别是局部复核场景，应允许 Provider 常驻，避免历史上“一窗口一次冷启动”的浪费。
