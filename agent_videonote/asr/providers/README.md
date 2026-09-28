# asr/providers

具体识别实现放这里。

每个 Provider 必须：

1. 有唯一 `provider_id`；
2. 声明 capability；
3. 接受统一输入；
4. 返回统一 Transcript；
5. 自己管理模型加载与资源生命周期；
6. 不直接推进任务状态；
7. 不知道 MCP 或最终交付格式。

目录可以按 Provider 独立拆分，但不能把品牌逻辑写进 workflow/application。
