# ADR 0025: Shared atom position mutation

- Status: Accepted
- Date: 2026-09-28
- Extends: [ADR 0005](0005-responsibility-based-editor-boundaries.md)

## Problem

Pointer movement and `history_atom_position_restore` separately coordinated atom
positions, stored depth, labels, marks and geometry invalidation. General
selection transforms also called the history-specific helper. A position policy
change required checking both implementations.

## Decision

`CanvasMoveController` owns both relative movement and absolute position
application. Both use its coordinate update operation. Explicit 3D values restore
exactly; otherwise screen translation preserves depth and projection residuals.
Absolute application relayouts labels and restores attached marks from their
saved offsets, while pointer movement retains its existing graphics translation
optimization. History and selection transforms call this owner directly; the
separate history position helper is removed.

History capture, commit and rollback remain with callers. Persistent camera state
and gesture state are unchanged. Read-only projected bond geometry remains a
rendering responsibility.

## Verification and limits

Perspective movement tests compare relative and absolute application for both
consistent and stale projections. Existing movement, transform, label, history
atomicity and document round-trip tests cover the callers. This change does not
introduce a general transformation framework or move rendering policy into the
mutation owner.
