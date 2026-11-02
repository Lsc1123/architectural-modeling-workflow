# 场景、相机、剖切与隐藏

适用：核查截图、场景保存和“缺构件”诊断。官方：[Page](https://ruby.sketchup.com/Sketchup/Page.html)、[Model#drawing_element_visible?](https://ruby.sketchup.com/Sketchup/Model.html#drawing_element_visible%3F-instance_method)。Page 自 SU 6，可见性路径查询自 SU 2020；SU 2026 场景相机等修改应进入事务。

```ruby
m = Sketchup.active_model
# parent 与 child 是已定位的根/子实例。
path = Sketchup::InstancePath.new([parent, child])
visible = m.drawing_element_visible?(path)
section = m.active_entities.active_section_plane
camera = m.active_view.camera
puts({visible: visible, section: section&.persistent_id,
      eye: camera.eye.to_a, target: camera.target.to_a})
```

有效显示需同时考虑对象、祖先、标签、场景与剖切；隐藏不等于删除。当前相机与场景保存相机分别检查。临时诊断截图不自动新增持久场景。`zoom_extents` 会改变当前视图，截图工具因此不能标成纯读取；截图之后若再保存场景，应重新绑定最终模型证据。
