# ADR 0060: Editable native CDXML straight annotations

- Status: Accepted
- Date: 2026-10-22

## Context

The preserving importer displayed all native graphics as raster projections.
Ordinary ChemDraw lines and arrows consequently lacked Chemvas endpoint editing.

## Decision

Map representable straight lines, dashed/bold lines, full-head arrows and
same-sided half-head equilibrium arrows to the existing Arrow record owner.
Keep native IDs and XML in the existing CDXML provenance. The native writer
updates endpoint coordinates and color while retaining unrelated metadata and
reaction references, including transitive legacy line aliases. Previously saved
native image snapshots are promoted while preserving edits and group membership. Unchanged source
objects retain every non-Z attribute, including the exact spelling of decimal
coordinates. The document-save boundary has a bounded graphical exception: missing,
tied, nonpositive or oversized Z values may be normalized to unique positive
INT16 ranks from the scene's painted order. Hidden fallback records reserve ranks
without constraining visible ink. Transparent carbon hit targets likewise retain
their native node slots without imposing overlap or interleaving constraints.
Already unique valid native ranks remain unchanged. Overlapping explicit native
order cannot be reversed; orders that cannot be represented or reconstructed are
refused before file replacement. This clarifies source preservation rather than
authorizing changes to geometry, styling, chemistry or references.

When reconstruction needs them, resolved ranks are retained in the embedded
snapshot's existing native XML and restored through its existing source-ID
bindings within the editor's paint layers. Otherwise its provenance remains exact.
The graph IDs, model array order, edit baselines and snapshot schema stay unchanged.
The serializer verifies overlapping painted bounds against a reconstruction before
writing. New objects without source bindings and arbitrary changes across paint
layers have no persistent order field in this format; if reconstruction changes
their overlap order, saving is refused with the destination unchanged. Bounds are
conservative and do not establish exact pixel-level occlusion for every shape.

Shared scene rendering derives stroke metrics from
native provenance, so editor and export use the same vector annotation.

## Verification and limits

`tests/test_cdxml_editable_arrows.py` covers import, endpoint/color edits, native
IDs, aliases, vector metrics and save/reopen, including overlapping arrow/fill
pixels and transitive fallback preservation on bare-native reopen.
`tests/test_cdxml_document_paint_order.py` covers transparent hit targets,
paint bounds on both sides of an overlap query, rebuilt crossing bonds through
save/reopen/save and session recovery of the resolved snapshot, and atomic refusal
of unrepresentable order. Deletion regressions remain in
`tests/test_cdxml_delete_aliases.py`. Decorative arcs, arbitrary Beziers and
unsupported head styles remain source-preserving image projections. Unsupported
style conversions and inline labels fail before replacing the saved file.
