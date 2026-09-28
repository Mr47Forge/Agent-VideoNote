# application

只负责用例编排，不实现底层算法。

当前拆分：

- `task_ops.py`：任务准备 / 状态摘要
- `transcript_ops.py`：字幕、主转写、局部复核、分段读取
- `delivery_ops.py`：视觉阶段收口、交付校验
- `health_ops.py`：不加载模型的启动体检
- `service.py`：薄门面，只做依赖组合

CI 会阻止业务逻辑重新塞回 `ApplicationService`。
