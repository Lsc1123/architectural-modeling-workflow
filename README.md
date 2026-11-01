# 建筑建模工作流 · Architectural Modeling Workflow

用自然语言协作推进建筑方案：**前期探索 → 选定方案 → 深入推敲 → 最终精修 → 出图交接**。SketchUp 承担建筑主模型，Blender 在独立进程中制作和续改可编辑资产，MCP 负责实际执行、项目状态、核查与恢复。

[English](docs/README.en.md) · [阶段与示例](docs/workflow.md) · [工具协议](docs/protocol.md) · [验证范围](validation/README.md) · [许可证](LICENSING.md)

## 能完成什么

- 从任务书/场地开始，也能接续用户草模和手改；已有事实底表可作为唯一语义来源。
- 创建原生墙板、带洞楼板及直梯，按宿主开洞、修复、变换、组合和赋材；特殊造型走受修订与范围约束的 Ruby 脚本。
- Blender 独立创建/续改 `.blend`，保留部件、修改器和材质，生成 GLB、DAE、贴图与预览；另起进程重读，再在 SU 验证。
- 对真实几何检查拓扑、实体碰撞、楼板面层/板厚、明确路径的净空与脚下实面、水平支承、声明的家具动作状态、实心防护和范围外变化。
- 保存、真实关闭重开，导出原生面环/实例/材料/相机/场景/切面，冻结证据并交给出图工作流。

用户负责选案、重大空间变更和最终交接，阶段内常规建模、修复和检查由 AI 连续执行。具体已验证能力以 [验证记录](validation/README.md) 为准。工具不能自动推断所有房间语义或任意生活动作，结构计算、施工深化及法规核定保持明确专业状态。

## 安装（macOS 首发）

需要 Python **3.12**、SketchUp 桌面版和 Blender。首版验收目标为 SketchUp **26.0.428** 与 Blender **4.5.12**；其他环境分别列验证状态。应用不随仓库分发。

```bash
git clone https://github.com/Lsc1123/architectural-modeling-workflow.git
cd architectural-modeling-workflow
python3.12 -m venv .venv
.venv/bin/python -m pip install --require-hashes -r requirements-lock.txt
.venv/bin/python -m pip install --no-deps -e .
.venv/bin/python scripts/package_release.py
```

1. 在 SU **扩展程序管理器 → 安装扩展** 中选择 `dist/amw-sketchup-0.1.0.rbz`；也可使用带备份的 `scripts/install_sketchup.py`。这是未签名的本地开发扩展，不要为它降低系统安全设置。
2. 重启 SU，打开要接续的模型，选择 **扩展 → AMW → Connect project** 并选择项目工作目录。
3. 添加 stdio 服务。下方解释器和工作目录须替换为本机实际路径：

```bash
codex mcp add architectural_modeling_workflow -- /absolute/repository/.venv/bin/python -m amw.cli serve --workspace /absolute/project
```

其他客户端运行 `.venv/bin/amw config --workspace /absolute/project` 可取得标准 `mcpServers` JSON。Blender 不在默认位置时加 `--blender /absolute/Blender`。

4. 将 `skills/architectural-modeling-workflow` 安装到 agent 的技能目录，或在聊天中引用其中的 `SKILL.md`。
5. 运行 `.venv/bin/amw doctor --workspace /absolute/project`，核对连接与活动文档。

MCP 服务不需要独立的 LLM API 密钥。可信 Ruby/Python 脚本拥有原生进程权限，目录检查和模型回滚不是系统安全沙盒。

## 自然语言使用

> 使用 architectural-modeling-workflow。先读任务书和场地，比较两个真正不同的剖面关系；我选定后再深入推敲。

> 接续当前草模，核对未保存修改、底表和实际标高。保留总体空间与手改，只精修入口门、落脚平台和相邻短梯，完成相关板、面层、围合、防护及通行核查。

> 在 Blender 独立文件中制作可续改的桌椅资产。记录尺寸、原点、朝向、安装基准和许可，导入 SU 后检查落地、拉椅和通道，最后保存重开。

已有项目直接从实际阶段进入。阶段模板和完整规则见 [工作流](docs/workflow.md) 与技能目录。

## 恢复与证据

写操作携带 `expected_revision` 和唯一 `operation_id`；超时先查询同一次操作，不能换 ID 重复写入。版本冲突先保全手改。失败事务回滚，写前副本留在 `.amw/backups/`。Blender 输出用新修订路径，取消或失败的输出无效。

分别记录设计确认、几何、文件重读、原生编辑和显示；范围分为新查、凭真实依赖比较继承、失败和未查。所有写回后保存重读，再冻结证据。文件哈希只证明来源，局部通过不代表全屋。门洞须联查门内转身、门外站稳、梯口转向与脚下实面。

## 开发与案例

```bash
.venv/bin/python -m pytest -q
.venv/bin/python scripts/package_release.py
.venv/bin/python -m build
```

`src/amw/` 为状态、协议与几何检查；`adapters/` 为软件适配；`skills/` 为协作方法。真实软件测试在独立工作区显式运行，普通 CI 不启动用户应用。见 [贡献说明](CONTRIBUTING.md)。

Plan E Unified、Split 使用独立发布副本，完整模型及精选证据通过 Release 提供；案例保留未决项，不将历史“完成”声明当作验收。[案例索引](examples/README.md)。原始聊天仅留本地。

核心/MCP/SU 为 MIT；调用 `bpy` 的部分为 GPL；原创模型/案例为 CC0，第三方资源保留原许可。见 [许可映射](LICENSING.md)。
