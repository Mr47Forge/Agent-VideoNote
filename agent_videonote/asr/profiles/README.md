# asr/profiles

配置“能力角色 → Provider”。

角色示例：

- `primary`：主时间轴生成
- `review`：局部独立复核

这里不实现识别算法。

Profile 应允许：

- primary 和 review 使用不同 Provider；
- 两个角色使用同一个 Provider；
- review 关闭；
- 不同机器使用不同配置；
- 后续新增角色而不破坏旧任务协议。
