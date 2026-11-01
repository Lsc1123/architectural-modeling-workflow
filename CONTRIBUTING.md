# Contributing

Use Python 3.12 and the pinned official MCP v2 SDK. Run `python -m pytest -q` before submitting changes. The Python service, state machine, software adapters and geometry checks are separate modules; keep software-specific calls in the adapters.

For a bug report include the application/OS versions, operation ID, scoped task, expected/current revisions, durable receipt and a minimal redistributable model. Remove personal paths and credentials. A timeout is not evidence that a write failed: recover the original operation first.

For native changes run the opt-in scripts in an isolated SketchUp workspace. State clearly whether evidence is an automated geometry test, a real software test, a GUI edit/undo check, or an unverified assumption. CI does not certify SketchUp or Blender behavior. Preserve failures and record manual corrections. Use three clean repeats for a release validation record.

Keep project dimensions and example-specific identities out of general algorithms. Reproduce a historical defect before proving its repair. Do not weaken tolerances, remove obstacles or expand exemptions merely to turn a result green.

Contributions use the license assigned to the relevant path in `LICENSING.md`. Include original source/license records for external assets and disclose incompatible or unknown provenance before adding files. Do not submit raw private chats or vendor SDK/application binaries.
