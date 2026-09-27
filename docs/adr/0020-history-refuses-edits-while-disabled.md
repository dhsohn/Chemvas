# ADR 0020: History refuses edits while it is disabled

- Status: Accepted
- Date: 2026-09-27
- Extends: [ADR 0002](0002-single-rollback-kernel.md)

## Problem

ADR 0002 keeps enabling and disabling the undo history but does not say what
an edit does while history is disabled. `CanvasHistoryService.push` returned
False then, each editor decided what to do with that, and at bd6101fd three
rules coexisted, each pinned by tests:

- Apply the edit without recording or publishing it: editors that record
  through `CanvasHistoryRecordingService` (structure building, atom labels,
  template and SMILES insertion, paste, bond updates), deletes, note commits,
  arrow labels, added shapes, brackets and orbitals, and the shape stroke.
  Several of them raised only when `push` returned False and
  `is_enabled()` was true, which cannot both hold.
  `test_group_membership_delete.py::test_intentionally_disabled_history_still_allows_unrecorded_group_shrink`
  pinned this rule.
- Refuse the edit and roll it back: image, stacking and layout edits raised
  `ValueError("History is disabled; …")`; group, transform, drag, rotation,
  color, style, mark and calculation plan edits raised `RuntimeError`.
- Apply the edit and publish a document change: the bond length, since
  8d98f560, and the sheet setup, pinned by
  `test_bond_length_workflow.py::test_length_change_publishes_when_history_is_disabled`
  and
  `test_sheet_setup_history.py::test_sheet_change_with_explicitly_disabled_history_is_allowed`.

The record does not say why the rules differ.

`CanvasDocumentSessionService.apply_state` is the only production caller of
`set_enabled`. It disables history from before it detaches the previous scene
until the replacement is committed or the previous document is restored. In
that window it clears the scene, draws the saved state
(`populate_document_scene`), restores groups and applies the sheet rectangle;
none of these calls an editor. It replaces a document in a new canvas, in the
one empty canvas that `reusable_open_target` accepts (a note being edited is a
document note, so that canvas has none), or in the CLI's `offscreen_canvas`,
whose layout and template edits run after `apply_state` returns. Tracing
every `push` while each test file ran offscreen found none during
`apply_state`.

## Decision

`CanvasHistoryService` owns the rule. While history is disabled, `push` and
`push_many` raise `RuntimeError("History is disabled; the edit was not
applied.")`, and the editor's transaction restores the document. Editors no
longer inspect the result of `push`, which returns None, or the enabled
state.

Because no editor runs while history is disabled, refusing is fail-closed and
changes no behavior a user can reach. The alternative, applying the edit
without recording it and publishing one document change, would be needed
only if document replacement edited through an editor, and it does not.

## Verification and limits

- `tests/test_history_disabled_rule.py` shows that a refused push leaves both
  stacks and the change listener untouched; that one editor of each former
  rule (structure, atom label, delete, note formatting, shape, bond length,
  sheet setup, image) refuses, restores the document, publishes nothing and
  succeeds once history is enabled; that replacing a document with every
  annotation family (`tests/fixtures/document-v8/extended.chemvas`) pushes
  nothing; and that an edit made during replacement restores the previous
  document.
- Tests that simulated a declined push by returning False from `push` now
  disable history, the only way the service declines one.

An editor that a future loading step calls while history is disabled makes
the document replacement fail and restore the previous document, instead of
keeping an edit that Undo cannot reach. Image, stacking and layout no longer
have their own warning text for this case, which only a disabled history
reached.
