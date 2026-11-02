# 面、孔洞与实例

适用：可推拉构件、孔洞及共享定义。官方：[Entities](https://ruby.sketchup.com/Sketchup/Entities.html)、[Face](https://ruby.sketchup.com/Sketchup/Face.html)、[Group](https://ruby.sketchup.com/Sketchup/Group.html)。基本方法自 SU 6；本例按 SU 2026 核对。

在已有 AMW 事务内，用独立组制作带真实孔洞的面：

```ruby
g = Sketchup.active_model.entities.add_group
outer = g.entities.add_face([[0,0,0],[4.m,0,0],[4.m,4.m,0],[0,4.m,0]])
inner = g.entities.add_face([[1.m,1.m,0],[2.m,1.m,0],[2.m,2.m,0],[1.m,2.m,0]])
inner.erase!
raise 'Expected one inner loop' unless outer.loops.length == 2
outer.reverse! if outer.normal.z < 0
outer.pushpull(0.2.m)
raise 'Not a native solid' unless g.manifold?
```

孔洞不是贴黑面；导出保存 outer_loop 与内环。修改现有组先 `make_unique`；组件是否共改由设计作用范围决定，不能随意更改所有实例。清理共面边前检查材质/UV与孔洞边界，不能把所有三角线直接删除。
