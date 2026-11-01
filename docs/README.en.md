# Architectural Modeling Workflow

A natural-language architectural workflow with an executable stdio MCP service: exploration, scheme selection, development, refinement and drawing handoff. Users choose schemes, major spatial changes and final handoff. Routine modeling and scoped checks run continuously.

SketchUp holds the editable building model. Blender runs independently for editable assets. The Python 3.12 service uses the official MCP Python SDK v2 and separates project state, geometry algorithms and software adapters.

Follow the [Chinese quick start](../README.md): install Python dependencies and package, install the SketchUp RBZ, connect a workspace from **Extensions → AMW → Connect project**, then configure a stdio client:

```text
/absolute/repository/.venv/bin/python -m amw.cli serve --workspace /absolute/project
```

Use `amw config` for standard MCP JSON and `amw doctor` for diagnostics. The agent skill lives in `skills/architectural-modeling-workflow`.

Tools cover native solids, scoped openings, transforms/materials, trusted scripts, independent Blender jobs, geometry checks and immutable handoffs. Writes require expected revisions and operation IDs. After a timeout recover the same operation. Reopening requires a new native document event, not activation of an existing window.

Checks cover their declared objects, routes, states and variants. A hash proves provenance, not correctness. Sampled operation states do not certify continuous human movement. Structural capacity, construction details and code compliance remain professional tasks. See [validation](../validation/README.md).

Plan E supplies separate Unified/Split release copies, selected process evidence and known limitations. Large files are Release assets. Raw private chats are excluded.

Core/MCP/SketchUp: MIT. Blender adapter and bpy fixture scripts: GPL-3.0-or-later. Original example models: CC0-1.0. External assets retain their original licenses. See [licensing](../LICENSING.md) and [contributing](../CONTRIBUTING.md).
