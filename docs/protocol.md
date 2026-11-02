# MCP 与数据协议 v0.1

服务使用 Python 3.12、官方 MCP Python SDK v2 和 stdio。一次进程绑定一个项目目录；标准输出留给协议，诊断与工作进程日志写文件。`amw://project` 资源提供当前事实及外部权威底表的实际内容。工具参数的机器可读定义见 `tool-schema.json`。

## 项目、阶段和证据

`project_init/get/update` 维护当前状态及 CAS 修订。`project_link_authority` 链接已有 JSON 底表；链接后禁止在运行时另写区域、关系和坐标表。外部变化先核对再刷新链接。每次有效状态变更保留 `.amw/project_history/` 快照和理由。

`decision_record` 记录用户决定及来源，当前决定可被明确替代；待定建议不能废止已确认决定。`user_source` 是宿主提供的可追溯引用，不是加密的用户授权证明。

`stage_check/advance/reopen` 检查或迁移阶段。选案需要用户选择；最终交接需要接受决定。进入已有阶段须提供实际交接依据。精修与交接还必须为每个模型声明所需检查范围，例如：

```json
{
  "requirements": {
    "refinement": {
      "main": {
        "layout_review": ["living-layout"],
        "circulation": ["entry-turn", "upper-landing"],
        "native_editability": ["root/123"]
      }
    },
    "handoff": {
      "main": {
        "geometry": ["root/123", "root/456"],
        "usage": ["entry-turn", "chair-pull"],
        "scope_diff": ["root/123", "root/456"],
        "file_readback": ["main-model"],
        "native_editability": ["root/123"],
        "display": ["complete", "entry-detail"]
      }
    }
  }
}
```

模型标签对应 `models` 键，范围对应报告的实际 `scope`。按任务书建立检查范围，不为通过而删减要求。多模型分别核对，不能用 Split 的证据代替 Unified；缺失或过期范围会阻止迁移。阶段工具验证证据记录及绑定，不替代设计判断。

报告 schema 1 包含 `kind/status/scope/sources/method`；sources 每项为项目相对 `path` 与 SHA256。设计确认、几何、文件重读、原生编辑、显示分别登记。`evidence_register` 只绑定真实报告，不证明操作者写下的断言。

`checks_run` 从保存后真实几何产生新报告，记录依赖 ID 和语义基础。`evidence_inherit` 要求原报告通过、完整依赖不变、原始来源有效且语义基础一致，再比较真实几何与应用材质/UV；继承保留原检查边界。哈希一致仅证明来源。

## SketchUp 适配

Ruby 扩展在原生 UI 事件循环轮询 `.amw/runtime/sketchup/queue/`。`sketchup_state` 返回进程、版本、活动文档身份、路径、未保存状态、外部磁盘变化、修订及场景。修订包含文档 ID；单位交换为米，原生 API 英寸转换显式处理。

写操作携带 `expected_revision` 和唯一 `operation_id`。请求内容与 ID 绑定，异参重用被拒绝；相同请求恢复同一回执，不再写入。`replayed` 标记历史回执，其 `state` 是原操作完成时快照；后续写入前重新读取当前状态。超时调用 `native_job_status`，未知结果禁止换 ID 重试。排队任务可取消；运行中原生事务等待完成，再按需撤销。

常用接口为 create、opening/restore_opening、transform、combine、material、delete、scene、import、save/reopen/export/capture。`shape` 支持 box、米制多边形含洞棱柱及直梯；直梯 n 个高差对应 n−1 个踏面，最后一级由到达板提供。

开洞限定实际宿主，修改前保存窗口副本，原生事务失败回滚，范围外变化拒绝提交。当前 typed replacement 对带逐面材质/UV 的宿主拒绝重建，typed union 限未涂装实体；需保留这些信息时使用可信原生脚本，不能静默丢材质。

`sketchup_script` 在同样修订、范围和事务约束下执行工作区 Ruby。它不是系统安全沙盒。全局文件副作用或任意 Ruby 行为不由模型撤销保护。创建场景、编辑探针及其他写回均在最终保存冻结前完成。

新建/重开跨原生事件循环等待真正文档事件。重开先确认无未保存修改，再关闭目标并读取；仅激活现有窗口不能计为文件重读。导入使用组件定义并显式创建实例，不能把鼠标放置模式启动当作导入完成。

## Blender 资产任务

`asset_build(specification, operation_id)` 在独立进程和新输出路径运行。最小例见 `examples/fixtures/table.json`：asset_id、blend、parts/source/script，及可选 glb/dae/preview、materials、anchor、sources。source 需要 expected_source_sha256；script 记录内容 SHA。输入变动或输出已存在/被预约时拒绝启动。

部件支持 box/cylinder/tube、已有部件 transform/delete；复杂造型用可信 Blender Python 脚本。可导入登记原许可与源哈希的 GLB/glTF、OBJ、FBX；具体往返验证范围见验证表，格式入口可用不等于任意素材已验收。

资产登记米制边界、原点与朝向、落地/安装基准、部件及修改器、材质和许可来源。保存 blend、导出 GLB/DAE、复制直接基础色贴图与 UV、生成 CPU 预览，再新进程重开 blend 和重导 GLB。复杂节点材质须先烘焙，DAE 不宣称完整 PBR 等价。

`asset_job_status/cancel` 使用持久回执和自有工作进程组。退出成功、结果成功及新进程复读均通过才记完成。取消或失败输出无效，不覆盖旧资产；超时查询同一任务。SU 实际导入、摆放、编辑及使用核查独立执行。

## 几何与检查边界

geometry schema 1 为世界坐标米制，包含 source、document、objects、materials、scenes、sections。对象保存稳定语义 ID 与原生 persistent instance path；vertices/triangles 是世界几何，faces 是原生内外面环及材料/UV，world_transform 为列主序仿射矩阵，平移单位米。

- topology：声明实体的闭合、方向与退化。
- collisions：真实闭合网格求交；开放几何保持未证实，不能记零碰撞。有意连接按对象对声明。
- floor：实际水平面环覆盖、洞及板厚；项目设计轮廓与测量容差显式传入。
- passage：声明水平路线的扫掠身体、障碍与脚下实面；每级梯、转向及门扇状态另列，不自动推断所有路径。
- support：声明高度处的真实水平接触面；墙装和承载能力另查。
- actions：移动部件在明确刚性状态下求交；中间连续动作仍未查。
- protection：声明直边的实心防护断面覆盖；竖杆间距、锚固和荷载不由此认证。
- scope_diff：比较世界几何、身份、材质及应用 UV，规范化面顺序与浮点表示；坐标精度 1nm，不能用范围豁免隐藏缺陷。

`drawing_read_slice` 将交接几何读取为平/剖切线底稿，不含消隐、标注和最终线型。复杂平面及关键剖面须实际试读。`handoff_export` 在阶段/所需范围通过后复制模型、几何、当前有效证据与源文件，复制后再核指纹；过期历史记录明确列出，失败包标 INCOMPLETE。

## 原生身份、脚本与精确范围

create/import 可赋 `semantic_id`，导入另有 `asset_id`；它们与 native persistent path 分开保存。sketchup_group 保留原生实例组织。sketchup_edit_context 进入/退出组编辑；最终 save 必须在根上下文且没有未结束的 GUI 动作。state 暴露 active_edit_path、实际相机和桥代码 SHA，save 的 freeze_ready 须为真。

脚本不得自行开启/提交事务、切换文档或编辑上下文。已有实体 scope_ids、允许新增根构件和 scene_names 须明确；未声明的几何或场景变化会回滚。变换要求可逆仿射矩阵。

topology 按连通壳与实际嵌套方向核对，正总容积不能掩盖反向第三体；旧对象缺少 expect_solid 时保持 unverified。treads 核对起点、每级及到达面的支承和竖向净空、高差与级数，不认证连续步态。passage 包含保守端点/转角圆形包络。checks_run 报告保留实际输入参数；scope_diff 另核对实例、切面和场景索引。交接包保留项目修订快照。

原生 export 同时写出实际纹理 PNG，记录工作区相对路径与 SHA；PNG 为原始像素，材质颜色和透明度另列。handoff 将这些文件一并复制并复核。写入前要求实际加载桥 SHA 与服务随包代码一致；更新后须保全并重启安装匹配的 RBZ。open 等到准确目标激活，不能当作重读；reopen 分事件循环关闭/打开并等待真正新文档事件。

## 兼容性补充（2026-11-02）

41个工具名、输入及结构化输出Schema保持不变。capture在原回执之外增加MCP ImageContent，供实际视觉检查；路径不代替看图。预期拒绝返回isError及原因，带请求ID时保留执行状态；快照未完成时另返回snapshot_operation，几何写入尚未提交。先查询该快照任务，解决后才恢复原客户端请求。

报告Schema仍为1，新增可选check_type明确算法。旧topology报告按已有method识别；未知geometry报告保守按空间检查处理。空间继承比较全部导出环境，含新增邻接；无已认证影响边界时，远处变化也会要求重查。不同模型路径须在项目修订历史中明确属于同一唯一模型标签，否则要求分版重查。继承保留原scope和parameters，不能扩大通过范围。
