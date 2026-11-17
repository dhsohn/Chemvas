# Working-document compatibility

[한국어](DOCUMENT_COMPATIBILITY.ko.md)

Chemvas opens and saves working documents as **CDXML (`.cdxml`)**. Existing
`.chemvas` files are no longer supported; renaming JSON to `.cdxml` does not
convert it. Existing files are not automatically modified or deleted.

New documents preserve all Chemvas editing state, including groups, formatted
notes, images, shapes, arrows, orbitals and settings, in an integrity-bound
snapshot inside the CDXML. Supported chemistry and graphics are native CDXML
objects. Unsupported drawing styles also carry a visual PNG projection.

ChemDraw and other editors can read the native representation. Editing native
XML invalidates Chemvas's snapshot, so reopening uses the externally edited
objects. Chemvas-specific grouping, settings or objects represented by images
may therefore lose their original editing behavior after a round trip through
another editor. A Chemvas save/reopen retains the full editing state.

Imported single-page CDXML preserves original native definitions, including
objects outside the editable drawing projection. Unsupported destructive edits
fail before replacing the destination file. Binary CDX and multipage CDXML are
not supported.

Native caption runs retain their fractional point sizes, normal/bold/italic
faces and baseline anchors. The editor and figure exports use the same precise
layout; font availability and platform rasterization can still affect glyphs.
Whole-note copying carries the caption's placement and font defaults into the
destination document, including through Undo/Redo and save/reopen. Note box
padding and border widths remain scene dimensions at either precision scale.
Minimum-font SVG/PNG checks include native atom runs and their script sizes.
Older Chemvas snapshots containing pixel-sized captions retain their existing
size. Imported dashed drawing strokes use equal dashes and gaps from inherited
`HashSpacing` (2.5 points by default); raster-only decorative projections retain
their pixel quantization. These display corrections do not rewrite untouched
native XML.

MOL remains an import format; its working copy is saved as CDXML. SVG is figure
output only; embedded Chemvas editing metadata is no longer read or written.
Plain SVG, PDF and PNG remain figure export formats. Internal JSON snapshots
are used for undo, clipboard and crash recovery, not as user document files.

See [ADR 0059](adr/0059-cdxml-only-working-documents.md).
