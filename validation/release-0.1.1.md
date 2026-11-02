# v0.1.1 release validation — 2026-11-02

This is the new release record. [v0.1.0 records](README.md#v010-历史验收) and its downloadable examples retain their original version and scope. The [optimization record](optimization-20261102.md) describes the preceding implementation checks.

Environment: macOS 27.2, SketchUp 26.0.428, Blender 4.5.12 LTS, Python 3.12.13, official MCP SDK 2.3.0. Native runs used a separate, disposable workspace. The loaded bridge reported `0.1.1`; its SHA-256 was `cbf0e4b2e7dba70a51d1b0f3d0a224e2abb2d67d32d5118045f558288c2acbc7`, matching the packaged source.

| Newly tested | Result and scope |
|---|---|
| Core / protocol / packaging | 50 tests passed: the 43 implementation tests plus seven release/version/archive checks |
| Independent baseline helper | Eight tests passed |
| Compatibility | All 41 tool names and input/output schemas retained; optional report `check_type` added; capture also returns MCP image content |
| Native SU, three clean repeats | `validate_native`, `validate_recovery` rounds r01–r03: modification, opening/restoration, same-ID replay, stale revision refusal, scope rollback, grouping/undo, face edit/undo, save and actual close/open |
| Blender, three clean repeats | `validate_asset`, `validate_continuation` rounds r01–r03: new five-part table, independent file reopen and GLB reimport, source-preserving continuation from 1.20 to 1.32 m, retained bevel, SU import/support and save/reopen |
| API and images, three repeats | `validate_api_reference` rounds r01–r03: native faces/holes, nested transforms, material/UV, visibility, save/reopen; 800×600 PNG MCP content byte-matched the actual saved capture |
| Native GUI | Mouse Push/Pull increased a cube from 1.0 to 1.2 m; keyboard Cmd-Z restored all exported geometry/materials. The second cube and scene remained unchanged. This is one GUI sample, separate from the three API rounds |
| Wheel installation | Independent Python 3.12 environment; stdio launch from outside the repository; 41 tools, one readable initialized-project resource, packaged adapters and skill/API references found |
| RBZ | Extracted into a temporary plugin directory; bridge loaded from that candidate and verified by version and SHA. Long-term installed extension files were not replaced |
| Distribution | Wheel, source archive, RBZ, skill ZIP and SHA256SUMS.json; archive members, licenses, skill-relative links and checksum coverage checked. No raw chats, native run logs or temporary test models distributed |

Local raw evidence is retained under ignored `validation/local/release-0.1.1/`: per-round `validation.json`, the GUI comparison, bridge preflight, installation record and final online-download check. Public summaries omit local user paths.

## Failures retained and corrected

- Initial GUI setup used a name containing spaces as an operation ID; it was rejected before submission. The fixture was then created with valid IDs.
- An initial GUI comparison helper imported a nonexistent helper module; no model write occurred. The comparison was rerun using the real canonical `scope_diff` implementation.
- A first wheel resource probe read the current-project resource before initializing its disposable project. The corrected probe initializes the project before reading the resource.
- The sandbox prevented dependency downloads for an isolated build. Building with already installed build dependencies and installing cached dependencies into a fresh environment succeeded. These are not native geometry failures.

## Inherited and unverified

The full five-stage pavilion and Plan E building cases were not regenerated. They remain explicitly v0.1.0 artifacts; their historical evidence is not renamed as v0.1.1 validation. This release freshly tests synthetic fixtures and changed workflow behavior, not whole-building circulation.

Windows, other SketchUp/Blender versions, arbitrary imported assets, continuous human motion, complete shader equivalence, structural/fire/acoustic performance and construction/code compliance remain unverified. Spatial evidence inheritance is intentionally conservative: a changed exported neighbor may require recalculation even when distant. CI runs core/protocol and distribution checks; it does not certify native desktop software.
