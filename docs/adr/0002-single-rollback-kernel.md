# ADR 0002: Single rollback kernel with fail-closed recovery

- Status: Accepted
- Date: 2026-07-24

## Context

ADR 0001 requires that "transaction capture, commit, rollback, and recovery
policy have one owner." Today that policy is spread across roughly 26,000
production lines in ten-plus modules (`core/history`, `ui/history_commands`,
`ui/canvas_history_service`, `ui/canvas_history_recording_service`,
`ui/history_push_failure_recovery`, `ui/canvas_delete_transaction`,
`ui/canvas_scene_reset_service`, `ui/canvas_document_session_service`,
`ui/selection_drag_tool`, `ui/selection_rotation_preview_transaction`,
`ui/transactions/*`), with at least four independent implementations of the
same scene/history exactness snapshot.

A repository-history audit established that this machinery was introduced by
adversarial design reviews (#49/#50), not by observed failures: the issue
tracker has no undo/redo or data-loss reports, and the only observed history
defects were an undo-granularity bug (fixed by `CompositeCommand`) and a
failed template build recorded as a successful action — neither a rollback
or corruption failure, and neither fixed by this machinery. The defensive
layers guard against in-process adversaries — attribute descriptors that
lie, setters that mutate and then raise, callbacks that re-enter
mid-transaction — which cannot occur with the production types: the canvas
is always a `CanvasView(QGraphicsView)` whose scene is a plain
un-subclassed `QGraphicsScene`; no production class overrides the guarded
Qt ports except `AtomLabelItem.setFont` (a benign relayout hook the kernel
must keep calling through the normal instance method); history state is a
plain dataclass with two `list` stacks; and the only change observer syncs
toolbar enablement, the bond-length spin box, and the tab's unsaved marker.

## Decision

### Threat model

The kernel defends against real failure modes only: exceptions raised by a
genuine bug part-way through a multi-step mutation, malformed `.chemvas`
payloads, and Qt object teardown (`sip.isdeleted`). Defenses against
in-process adversaries — lying getters, mutate-then-raise setters, hostile
`BaseException` subclasses, re-entrant transaction owners, replaced module
attributes, list/dict subclasses — are non-goals and are removed together
with the tests that construct those adversaries.

### One stack-policy owner

`CanvasHistoryService` owns every decision about the undo/redo stacks.
Snapshot restores report their outcome as an ordinary `RestoreOutcome`
return value; the ContextVar authority channel, its one-shot consume
function, and the legacy exception-attribute marker are removed. The four
parallel snapshots of the same plain history state (`HistoryAuthoritySnapshot`,
`_HistoryPublicationAuthority`, `RecordingHistoryPolicySnapshot`,
`CallbackFreeHistoryBaseline`) collapse into one small value object:
`(state, tuple(history), tuple(redo_stack), enabled, limit)`.

### One document-savepoint owner

One public module under `chemvas.ui.transactions` owns whole-document
capture/restore (today split between `history_canvas_access`,
`CanvasDeleteTransactionSnapshot`, `transactions/object_graph_snapshot`,
`transactions/history_command`'s frozen-payload capture, and the
underscore-prefixed `_SceneRuntimeSnapshot` toolkit that `history_commands`
exports to six modules). `history_commands` keeps only its command classes.
The automatic scene-rect guard stays a `chemvas.ui.transactions` module in
its reduced form and is owned by the savepoint owner. The private
per-module copies of the same snapshot patterns (rotation preview, document
session, delete/reset raw authorities, drag tool) become consumers of the
shared module or of the begin-state they already hold. `chemvas.ui.
transactions` is the transitional home; the final package follows ADR
0001's target shape when the cluster migrates. The stack-policy owner and
the savepoint owner are the two halves of ADR 0001's "one owner" criterion:
one owner per concern, with the stack owner calling the savepoint owner.

### Fail-closed recovery

A restore runs once and is verified once. On failure the kernel does not
retry silently, re-verify in alternating orders, or re-close snapshots
behind the propagating exception; it surfaces the original error (rollback
failures attached as notes), applies the conservative stack policy below,
and leaves durable recovery to autosave and session restore — the layer
built for it. Retries of infallible Qt calls, base-class port bypasses,
duck-typed alternative-name probing, and `BaseException`-swallowing
comparators are removed everywhere.

### Preserved semantics

The following user-visible behavior is kept exactly as it is today:

- Commands stay invertible: most store absolute before/after payloads; the
  move commands store relative deltas and rely on the whole-document
  savepoint for exactness (`history_transaction_owns_exact_state`).
  `CompositeCommand` rolls partially-undone children forward so the canvas
  never shows a state that neither stack describes.
- `RestoreOutcome`'s three-way distinction (authoritative / safe inverse
  fallback / unknown) — a failed absolute restore must not be followed by
  relative inverses.
- Failure stack policy: an exact command whose undo failed but whose
  savepoint restored authoritatively stays on the stack (retryable); other
  failures pop the command and clear the redo stack; legacy commands pop
  before applying.
- One whole-document savepoint per top-level exact operation, with nested
  commands deferring to the outer transaction.
- Document-open rollback restores the previous canvas with the original
  live `QGraphicsItem` objects (history commands hold item references), and
  a destructive `QGraphicsScene.clear` discards stacks that reference
  deleted C++ wrappers.
- Undo-history limit, enable/disable, and observer-exception containment.

### Open question

Whether a failed document open on a reused blank canvas must preserve that
canvas's undo/redo stacks (current behavior) or may clear them is a product
decision that has not been made yet. Until it is recorded, slices preserve
the current behavior.

## Migration

The reduction proceeds from lowest to highest risk: rotation preview, drag
tool, scene-rect/attach trackers (one slice — they share private imports),
delete transaction, scene reset, document session, and finally the kernel
consolidation itself, which also migrates the remaining
`history_push_failure_recovery` consumers (color mutation, atom-label
recorder, tool context).

The behavior contract of record is the characterization suite
(`tests/test_txhistory_characterization.py`) together with the surviving
real-Qt suites: `test_core_history_ui_atomicity.py`,
`test_gui_document_template.py`, `test_session_recovery_integration.py`,
`test_gui_smoke.py`, and the real-Qt portions of
`test_ui_history_command_atomicity.py`. Semantics that only
hostile-double tests pin today — the failure stack policy (retryable /
pop-plus-clear-redo / legacy pop-first), undo limit and enable/disable,
observer-exception containment, destructive-clear history discard, and
drag-gesture round-trips — must gain behavior-level coverage in the slice
that touches them, before their pinning tests are deleted. Every slice
keeps this contract green and records its own removal approval.

## Consequences

- `history_push_failure_recovery.py` and the recording service's
  verification lattice retire; recording shrinks to diffing and one push.
- Cross-module imports of underscore-prefixed snapshot helpers end; the
  boundary tests that froze the removed wiring retire with it.
- A genuine restore failure now surfaces one error with the conservative
  stack policy applied, instead of being silently repaired twice — failures
  become more visible, not less.
- The behavior contract of record for undo/redo, rollback, and
  document-open behavior is the suite set named in Migration, extended
  slice-by-slice — not the internals-pinning tests, which retire with the
  machinery they pin.
