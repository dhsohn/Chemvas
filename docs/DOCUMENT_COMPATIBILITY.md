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

MOL remains an import format; its working copy is saved as CDXML. SVG is figure
output only; embedded Chemvas editing metadata is no longer read or written.
Plain SVG, PDF and PNG remain figure export formats. Internal JSON snapshots
are used for undo, clipboard and crash recovery, not as user document files.

See [ADR 0059](adr/0059-cdxml-only-working-documents.md).
