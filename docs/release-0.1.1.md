# v0.1.1 — 工作流简化与证据继承修正

这是兼容更新，保留全部 41 个 MCP 工具名称及输入输出结构。

- 简化日常修改流程，集中通用硬规则，并提供五组按需读取的 SketchUp API 参考。
- 统一证据有效性与原操作恢复逻辑；空间核查继承会检查周边变化和模型版本关系，避免漏掉新增障碍。报告新增可选 `check_type` 字段，旧报告仍可读取。
- 截图工具在原回执之外直接返回 MCP 图像；预期错误与超时返回可操作的恢复信息。
- 统一 Python、MCP、SU 扩展及桥版本；CI 先构建全部附件，再生成并验证完整校验和。

验证：50 项核心/协议/发布测试、8 项独立基线测试；三轮 SU 原生修改与恢复、Blender 新建/续改及 SU 导入、API 示例与图像检查；另做一次鼠标编辑和键盘撤销，以及仓库外独立 wheel 安装。详见[本版验收范围](../validation/release-0.1.1.md)。

安装附件为 wheel、源码包、RBZ、技能 ZIP 和 `SHA256SUMS.json`。未变化的建筑、展亭和桌子案例继续从 [v0.1.0](https://github.com/Lsc1123/architectural-modeling-workflow/releases/tag/v0.1.0) 下载，不视为本版重新验收。

实测环境为 macOS 27.2、SketchUp 26.0.428、Blender 4.5.12 LTS、Python 3.12；Windows、其他软件版本和专业建筑合规未验证。更新后请重启并核对桥版本及指纹；不新增 PyPI 分发。
