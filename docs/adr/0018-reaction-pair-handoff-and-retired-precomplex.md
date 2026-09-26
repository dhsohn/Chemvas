# ADR 0018: Reaction-pair handoff and retired precomplex

- Status: Accepted
- Date: 2026-09-26

## Problem

The desktop Calculation dialog stopped at plan editing. Expanded hydrogen and
alias mapping errors appeared only when a user switched to `pack-step`. The user
wants to prepare a single reactant/product pair for external NEB work and remove
precomplex support. Existing durable documents still contain multi-step plans
and reviewed endpoint ensembles.

## Decision

A right-side dock exposes structures, atom review, then check/export. Atom
correspondence is edited on the existing canvas, not in a separate window. A
transient event filter consumes mapping clicks without forwarding drawing gestures;
Escape exits it, and overlays are removed on exit, panel hide or source change.
Canvas edits and document switches invalidate the checked snapshot and disable
old draft operations until an explicit reload. Save draft remains an undoable
plan mutation. The source snapshot is compared again before check/save/export.
The reusable form owns pair edits; the dock owns the active-document binding;
`calculation_canvas_mapping` owns the temporary input mode and its overlays.

Source
mapping, expanded geometry validation and researcher confirmation remain separate.
State IDs and component roles are optional detail. Existing plans remain editable
one pair at a time; the scope does not grow into calculation execution or planning.

`core.calculation_handoff` owns the existing Qt-free handoff builder. CLI dispatch
retains argument and file-boundary checks. A desktop QProcess invokes that CLI on
an exact private snapshot, keeping geometry work cancellable and outside the GUI
thread. Any edit invalidates the checked artifact and confirmation. The export
folder includes that exact source snapshot; creating an existing destination is
an error. Single-component XYZ rows use canonical path indices. Multiple components
remain separate, with their existing index maps, rather than invented assemblies.
The machine-observation v1 and elementary-step v2 contracts do not change.

Delete the precomplex geometry validator and placement profiles. The isolated
`domain.document.retired_endpoint_data` reader preserves historical v2 endpoint
JSON without interpreting scientific metadata. It checks the kind and ordinary
JSON encoding; the enclosing document owns file/structure bounds. No calculation
code interprets archived coordinates, selections, profiles or hashes. Existing
plan-edit invalidation still clears affected archives; unchanged saves retain them.
This preservation exception ends only when the durable v2 plan reader is retired.
A destructive conversion of stored documents is not part of this change.

## Verification and limits

Regression coverage exercises document/CLI compatibility, generated atom identity,
visual mapping, edit invalidation, worker cancellation and launch failure, source
hash binding, canonical XYZ ordering, no-overwrite and partial-publication cleanup.
Real RDKit end-to-end checks cover single and separate component exports and an
implicit hydrogen mismatch. The repository gate and native desktop checks are
required before completion. The check does not establish quantum convergence,
physical endpoint placement or a valid NEB path; users must review those externally.
