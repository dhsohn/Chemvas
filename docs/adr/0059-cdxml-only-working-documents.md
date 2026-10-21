# ADR 0059: CDXML-only working documents

- Status: Accepted
- Date: 2026-10-22
- Supersedes the `.chemvas` file contract in ADR 0058 and the working-file compatibility policy.

## Decision

CDXML is the only working-document file format. New documents, Save, Save As,
command-line document creation and editing, and browser downloads use `.cdxml`.
Existing `.chemvas` files are no longer supported. There is no compatibility
reader or automatic conversion in the public file workflows. Existing files
are not deleted or rewritten.

The internal versioned state schema remains necessary for undo, clipboard,
session recovery and integrity-bound CDXML editing metadata. Those JSON records
are not a second public working-file format.

Native CDXML nodes, bonds and supported graphics remain native. For drawing
styles with no supported native export mapping, the working document carries
an embedded PNG projection as well as its complete editable state. This avoids
inventing chemical semantics or preventing Save because a note, group, image,
orbital or decoration is present. Group membership and editor settings live in
the snapshot. Removing or changing native XML invalidates the snapshot; the
next open imports the native representation. Consequently, a round trip through
another editor can reduce such objects to their visual projections. Save in
Chemvas preserves them as editable objects.

Original imported CDXML continues through the source-preserving writer. It
retains unmodified native definitions and refuses unsupported destructive edits.
Working-document saving and strict publication export remain separate: the
latter keeps its explicit semantic and fidelity preflight requirements.

## Verification

Verify blank and mixed-element new documents, every arrow/orbital/bracket/shape
kind, group membership, text formatting, custom sheet settings, images, repeat
saves, malformed/renamed JSON rejection, save failures, CLI and browser routes,
and the installed desktop application. Full platform tests retain the public
workflow contracts while internal snapshot tests retain schema validation.
