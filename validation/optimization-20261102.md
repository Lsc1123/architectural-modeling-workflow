# Workflow optimization verification — 2026-11-02

Baseline: `02f9447`. The working tree keeps all 41 MCP tool names and their input/output schemas. The optional `check_type` report field identifies the original calculation when inheriting evidence; older reports remain readable.

## Changes

- Shared report/source/semantic freshness in `amw.evidence`, used by stage gates, inheritance and handoff; each caller retains its own scope requirements.
- Shared opening/restoration/union preparation: recover the original operation before exporting a fresh snapshot, then verify its revision.
- Direct check dispatch and dependency collection; removed unused imports and a redundant painted-solid predicate. No public modeling tools or standalone baseline entry points were deleted.
- Spatial inheritance compares all exported surroundings, including newly added objects. Different model files need a recorded common version lineage. Local topology can retain its original explicit scope.
- Explicit MCP annotations, structured expected errors, original-operation recovery information and real image content alongside capture receipts.
- Daily modification loop, shorter iteration card, [canonical hard rules](../skills/architectural-modeling-workflow/references/hard-rules.md), [classified lessons](../docs/history-lessons.json) and [five on-demand API topics](../skills/architectural-modeling-workflow/references/api/index.md).

Revision conflicts, idempotent operation recovery, unsaved-window protection, transaction rollback, out-of-scope comparison and real native reopening remain in place. Ordinary changes do not restart design stages, repeat baseline registration or generate a full handoff package.

## Tests performed this revision

Environment: macOS, Python 3.12, MCP SDK 2.3.0, SketchUp 26.0.428, Blender 4.5.12 LTS. Native tests use an isolated workspace and synthetic fixtures. The design project's models were not modified.

| Check | Result and actual scope |
|---|---|
| Python core/protocol | 43 passed, including all original 27 tests and 16 additional cases |
| Standalone baseline helper | All 8 original tests passed |
| Tool compatibility | All 41 names and input/output schemas match the baseline; annotations added |
| Freshness and inheritance | Changed source/report/semantics rejected; variant lineage checked; new obstacle blocks the same body and invalidates inherited spatial evidence; unchanged local topology remains eligible |
| Historical failure cases | Synthetic geometry recalculations cover old floor slots, missing door landing/support and damaged protection. Historical building reports were reviewed, not rerun on the complete building |
| SU native fixture | Creation, opening/restoration, same-ID replay, stale-revision refusal, out-of-scope rollback, grouping/undo, native face push/pull/undo, save and actual close/open passed |
| API examples | Face/hole, nested transform, front/back material/UV and visibility examples executed in SU 2026; save/reopen compared; transaction rollback/undo covered by the native recovery fixture |
| MCP capture | Actual 800×600 PNG image content returned and byte-matched to the saved capture; image visually inspected |
| Blender new asset | Five editable parts, retained bevel, saved `.blend` reopened in an independent process, GLB reimport, textured DAE import to SU, support, native edit/undo and reopen passed |
| Blender continuation | Original source unchanged; new editable file widened from 1.20 m to 1.32 m, retained bevel and passed independent reopening/export checks |

Local native evidence is under the ignored `validation/local/optimization-20261102/` directory: `native-r02/validation.json`, `recovery/r02/validation.json`, `api-reference/r01/validation.json`, `asset-rounds/r02/validation.json` and `continuation-result.json`. The local delivery entry holds the final code/package hashes, compatibility check and skill backup/synchronization record. Raw chats and operation logs are not distributed.

## Historical audit and limits

The earlier 43-chat audit was extended to 46 accessible historical chats. All active and archived index pages were compared; three archived chats were already covered, three new chats were added and two changed chats refreshed. The incremental pass contains 26 unique user messages, deduplicated by message ID with a text-hash fallback for one oversized local record. Attachment gaps and unfinished later corrections remain explicit. The public file contains only anonymized lessons and implementation references.

The first native attempt found no connected workspace and performed no write. The first Blender run crashed during Metal initialization inside the execution sandbox before modeling; the identical isolated task passed outside that sandbox. Both failures remain in local evidence.

This revision tests API-driven native editing and undo; it does not renew the older manual GUI gesture acceptance. Other operating systems, older application versions, arbitrary downloaded assets, general shader equivalence, whole-building circulation and professional construction compliance are unverified. Spatial evidence inheritance is deliberately conservative: without a certified influence envelope, even a distant changed object may require a fresh check. Hard rules about intent, privacy and appearance still require review; they are not all automatically enforced by geometry code.
