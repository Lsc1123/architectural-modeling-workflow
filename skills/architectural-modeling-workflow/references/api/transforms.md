# 嵌套变换与单位

适用：嵌套构件定位和跨软件导入。官方：[Transformation](https://ruby.sketchup.com/Geom/Transformation.html)、[InstancePath](https://ruby.sketchup.com/Sketchup/InstancePath.html)。Transformation 自 SU 6，InstancePath 自 SU 2017；SU 2026 对不可逆变换求逆会抛出错误。

```ruby
# parent 是根实例，child 是其定义中的子实例；point 为子实例局部坐标。
path = Sketchup::InstancePath.new([parent, child])
world = path.transformation * Geom::Point3d.new(1.m, 0, 0)
metres = world.to_a.map { |v| v * 0.0254 }
raise 'Unit conversion failed' unless metres.all?(&:finite?)
```

SU API 内部长度用英寸，AMW 交换数据用米；显示单位不会改变 API 单位。变换按父到子累乘，已导出世界坐标不可再乘一次父变换。AMW 的 16 元素矩阵为列主序、平移单位米。拒绝奇异缩放；镜像时另查面方向、法线和材质侧。
