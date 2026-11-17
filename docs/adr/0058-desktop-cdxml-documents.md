# ADR 0058: Desktop CDXML documents

- Status: File-format policy superseded by [ADR 0059](0059-cdxml-only-working-documents.md)
- Date: 2026-10-22
- Partly supersedes: [ADR 0030](0030-cdxml-export.md)

## Problem

The desktop exported CDXML but could not open it and save edits back. Real
research drawings also contain contracted fragments, reaction metadata, curves
and native object attributes that cannot be reconstructed from the editor graph.
A conversion-only importer would lose those objects and their relationships.

## Decision

Support `.cdxml` in Open, recent files and Save As, binding it to the existing
atomic save, duplicate-path, external-change and recovery workflow. Retain the
entire native XML as document content. Atom and bond bindings use source IDs;
annotation bindings follow stable runtime record identities and are serialized
alongside item arrays. The native writer updates changed objects by identity
and retains untouched subtrees, including nested chemistry and reaction steps.

The desktop displays atoms and captions using Chemvas styles. Native curves,
arrows, brackets, orbital outlines and colored molecular areas have bounded
raster editing projections; moving/resizing those projections transforms the
original vector coordinates when saving CDXML. The saved CDXML does not replace
these objects with bitmaps. It is not a pixel-identical ChemDraw renderer.
Native chemical properties, including fractional bond orders and contracted
fragment definitions, remain in XML independently of the drawing projection.

Embedded objects with a valid PNG preview display that preview while preserving
all original metafile representations. Custom canvases allow 10–3000 mm per side
to accommodate large native workspaces without changing their coordinates.

Document v10 stores `cdxml_source` and supports wavy/plain hash bond displays.
The native data survives CDXML saves and internal session recovery; readers
for v7–v9 remain supported. Format limits apply to the XML, item count and images.

CDXML Save also includes a validated Chemvas snapshot comment bound to the exact
native XML bytes by SHA-256. Reopening uses the snapshot only while the digest
matches. Native changes by another editor invalidate the snapshot and trigger
native import. This is editing metadata, not an authentication boundary.

## Supported editing and explicit limits

Single-page native documents support atom movement, elemental and generic R/X/A/Q
label replacement, bond edits within a native fragment, caption text/formatting,
and native vector-object movement/resizing. Existing contracted labels retain
their complete internal definitions. New elemental atoms, captions, basic
arrows and rectangles can be added. The native writer rejects operations it
cannot represent before atomic replacement, including unsupported new aliases,
cross-fragment connections, deleting objects still used by reaction/bracket
references, changing a native raster projection's pixels or opacity, and
unsupported new annotation types. Errors leave the destination unchanged.

Unrecognized object types, malformed XML, entity declarations, binary `.cdx`
and multiple pages are rejected before replacing the current canvas. The
existing CLI figure exporter is separate from native document preservation.

## Verification

Synthetic tests exercise nested chemistry, reaction references, no-edit native
XML preservation, coordinate transforms, rich-text edits, new objects, external
modifications, snapshot invalidation, recovery and Delete/Undo identities.
Private research samples are used locally without checking their contents into
the repository. Full `make check` and native UI verification are separate
acceptance steps. A self-roundtrip does not establish ChemDraw consumer behavior.

The mapping follows the archived ChemDraw SDK's [CDXML description](https://bobhanson.github.io/IUPAC-FAIRSpec/cdx_sdk/IntroCDXML.htm),
[node types](https://bobhanson.github.io/IUPAC-FAIRSpec/cdx_sdk/properties/Node_Type.htm),
[bond display](https://bobhanson.github.io/IUPAC-FAIRSpec/cdx_sdk/properties/Bond_Display.htm),
and [graphic geometry](https://bobhanson.github.io/IUPAC-FAIRSpec/cdx_sdk/properties/Graphic_Type.htm).

Native atom typography is derived from the owned XML when a scene is built.
Per-run font sizes and faces, text baselines, right-aligned chemical labels and
stacked hydrogens use the source layout in both live and detached scenes. The
projection follows atom moves; changing its text uses the ordinary editor label
layout, and restoring the source text restores its native typography. These
rendering projections do not add a second persisted source of truth.

Direct comparison with ChemDraw also requires per-bond dimensions: scaled
fragments can override the root line width, spacing, bold width and hash spacing.
The renderer derives these dimensions per bound edge and scopes them to each
build/update, restoring the ordinary renderer style afterward. Native captions
use scene-unit font sizes and baseline/justification anchors rather than Qt's
point-to-pixel conversion and document margins. Their transient placement leaves
the editable record coordinates intact. Pixel-sized caption runs are written
back as native point sizes on text edits. These changes were checked against an
actual ChemDraw 25.0.2 Scheme1 window, separately from roundtrip tests.
Figure1 was also compared in ChemDraw: source text rotation remains anchored at
its baseline, equilibrium shafts retain their head direction, and retained frame
projections honor rounded/dashed styling. Graphic previews remain bounded raster
projections, so this does not assert pixel-identical rendering across platforms.
