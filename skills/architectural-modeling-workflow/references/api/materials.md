# 正反面与 UV

适用：保留逐面贴图、材质及两面显示。官方：[Face](https://ruby.sketchup.com/Sketchup/Face.html#get_UVHelper-instance_method)、[UVHelper](https://ruby.sketchup.com/Sketchup/UVHelper.html)。`get_UVHelper` 自 SU 6；按 SU 2026 核对。

```ruby
# face 是已定位的原生面；读取其局部顶点的正反面 UVQ。
helper = face.get_UVHelper(true, true, Sketchup.create_texture_writer)
p = face.vertices.first.position
front = helper.get_front_UVQ(p)
back = helper.get_back_UVQ(p)
uv = [front, back].map do |q|
  raise 'Invalid UVQ' if q.z.abs < 1e-12
  [q.x / q.z, q.y / q.z]
end
```

`face.material` 与 `back_material` 分开保存，继承的实例材质也要解析。UVQ 需除 Q，不能当作普通 XYZ 变换。重建网格可能丢逐面映射；当前 typed boolean 对有材质宿主的限制应保留，复杂情况用受范围约束的原生脚本。反转面后重新核对两侧材质与纹理方向。
