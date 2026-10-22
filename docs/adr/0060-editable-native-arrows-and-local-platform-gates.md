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
objects remain untouched. Shared scene rendering derives stroke metrics from
native provenance, so editor and export use the same vector annotation.

## Verification and limits

`tests/test_cdxml_editable_arrows.py` covers import, endpoint/color edits, native
IDs, aliases, vector metrics and save/reopen. Deletion regressions remain in
`tests/test_cdxml_delete_aliases.py`. Decorative arcs, arbitrary Beziers and
unsupported head styles remain source-preserving image projections. Unsupported
style conversions and inline labels fail before replacing the saved file.
