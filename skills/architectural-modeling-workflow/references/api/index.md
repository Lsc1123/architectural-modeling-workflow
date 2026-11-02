# SketchUp API 按需索引

面向当前适配器的 SU 2026，官方文档核对日期 2026-11-02。历史最低版本仅描述 API 可用性，不承诺本工作流兼容旧版。示例为独立隔离样件；先在空白测试文件验证，不能直接粘贴到建筑主模型。

| 任务 | 读取 |
|---|---|
| 面环、真实孔洞、实体与组/组件 | [entities.md](entities.md) |
| 嵌套实例、坐标与单位 | [transforms.md](transforms.md) |
| 正反面、逐面材质与 UV | [materials.md](materials.md) |
| 事务、撤销、保存重开 | [transactions.md](transactions.md) |
| 场景、相机、剖切与隐藏 | [views.md](views.md) |

先查对应专题；未知方法、重载或版本差异再查官方页面。这里不复制完整 SDK，也不引入文档检索服务。AMW 的脚本工具已经包裹事务，勿在脚本内嵌套事务、切文档或改编辑上下文；保存/重开用对应 MCP 工具。
