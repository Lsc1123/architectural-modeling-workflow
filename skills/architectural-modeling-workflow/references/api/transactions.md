# 事务、撤销与真实重开

适用：独立 Ruby 工具事务和保存重读。官方：[Model](https://ruby.sketchup.com/Sketchup/Model.html#start_operation-instance_method)、[Sketchup.open_file](https://ruby.sketchup.com/Sketchup.html#open_file-class_method)。基本事务自 SU 6，`with_status` 重载自 SU 2021；按 SU 2026 核对。

仅用于独立控制台样件，**不在 sketchup_script 内重复包裹**：

```ruby
m = Sketchup.active_model
m.start_operation('Isolated sample', true)
begin
  m.entities.add_group.name = 'Editable sample'
  m.commit_operation
rescue StandardError
  m.abort_operation
  raise
end
```

撤销在独立事件循环调用，随后导出比较。保存成功不等于重开成功：核对路径、modified、磁盘变化，使用 MCP reopen 获取原生打开事件及新 document_id，再导出比较。不要用 `DefinitionList.load` 冒充当前文档重开，也不要在未保存窗口上直接 `open_file`。超时查询原 operation_id，不能新建 ID 重复写入。
