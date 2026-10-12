# ADR 0054: Bind CDXML meanings to a saved drawing snapshot

- Status: Proposed
- Date: 2026-10-12
- Extends: ADR 0053

## Problem

Deleting a bond leaves a tombstone in the editor's bond list. Saving writes a
compact bond array without renumbering the live editor, which is needed by
history and graphics. A version 2 documentary-contact binding correctly reviewed
against the saved file therefore names saved bond IDs. Previously the GUI checked
that file's digest but applied the contact to the live model. Immediate export
could refuse a valid contact that exported successfully after reopening.

## Decision

After the existing clean-snapshot and exact-file/sidecar digest checks, capture
the validated saved state as immutable JSON bytes together with immutable binding
records and one generation of export references. Binding checks, preflight and
serialization all consume a detached scene rebuilt from those saved bytes.

The common document scene owner builds and disposes this detached scene using
the caller's existing Qt application. The CLI reuses that same constructor;
platform/application setup remains in bootstrap. Desktop export never starts a
second application or changes the running Cocoa backend.

Runtime graphics are identified by saved document references: stable atom IDs,
bond order with tombstones omitted, and annotation document order. This mapping
moves visibility and selection onto reconstructed graphics; it never renumbers
the sidecar. Export items without a saved reference or missing from the rebuilt
scene refuse instead of disappearing. Saved groups are reconstructed against
the new annotation IDs so the existing scope-aware unsupported-group checks
still apply. Groups remain unsupported when they touch the export scope.

The live model, graphics, selection, history and source/sidecar bytes are not
rewritten. Canonical bond IDs are private to the detached export scene. Exact
ordered endpoints, order, style, atom visibility and selection-scope checks
remain in the existing CDXML exporter. Unsaved edits, saved edits with stale
bindings, external replacements and uncertain snapshots still refuse.

## Verification and limits

The regression in tests/test_cdxml_saved_snapshot.py deletes a preceding C-C
bond, saves, reviews v2 contacts with compact IDs and exports immediately and
after reopening. Whole-figure and selected exports must be byte-identical,
covering chemistry, coordinates, captions and styling. The live tombstone and
working Undo/Redo remain intact. Wrong contact slots pointing at another dotted
bond, reversed endpoints, changed order/style, hidden/out-of-scope labels and
groups in the selected scope must still refuse without publishing output.
A group outside selection must not prevent that selection's export.

A prepared snapshot is independent of subsequent changes to the live context;
a new GUI request after those changes still hits the dirty guard. This does not
authorize background GUI edits between validation and synchronous export.

The existing Ph v1 generic-aryl bindings contain no documentary contacts. Their
full-figure output is checked separately as a compatibility control. This change
does not relax any native consumer-reference, font, palette, chemistry or
bond-spacing checks.

