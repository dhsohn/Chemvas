# ADR 0053: Reviewed desktop CDXML and script geometry

- Status: Proposed for the review candidate; not released
- Date: 2026-10-12
- Extends: ADR 0047, ADR 0049

## Explicit saved-document meanings

The desktop Export Figure dialog accepts an explicitly selected reviewed label
binding JSON for CDXML. Each dialog starts with no selected binding. The same
bounded strict reader serves CLI and desktop; no interpretation is inferred.
Before exporting, the desktop requires a trusted clean snapshot, an exact saved
source digest, unchanged on-disk bytes, and a matching sidecar source digest.
Unsaved edits, saved edits with a stale binding, externally replaced files,
missing baselines and snapshot warnings refuse before output publication.
Validation and export run synchronously without processing UI events between
them. The export service retains its atom, exact-label and scope checks.
Selecting a binding never saves a document or rewrites the sidecar's digest.

## Shared annotation paint

`line_bold` is an annotation stroked with the common renderer's bold bond pen,
not a chemical Bold bond. Emit the existing native unheaded arrow using that
same centered, flat-capped width, directed endpoints and authored color.
Existing arrow-label, mirror and unsupported-kind guards remain.

Both HTML sub/sup tags and CSS vertical-align enter Qt's same QTextCharFormat
path. Native face bits 32/64 retain sub/superscript meaning, combined with bold.
Read the actual shaped glyph family and size, including existing bounded
fallback handling. Native script faces paint at 75 percent of their encoded
size, so compensate that factor before the existing twentieth-point rounding.

A line containing scripts emits separately positioned editable text runs to
retain Qt's shaped horizontal origins. Use the common note painter's fixed-point
baseline displacement, not a second approximation. Native subscript moves down
by full-size descent; superscript moves up by (em - descent)/2, reusing the common
atom baseline rule. Compensate these shifts in the text origin before applying
the existing uniform item scale and rotation. Normal lines retain their old
serialization. Ambiguous glyph origins and unsupported formatting still refuse;
no text is outlined, rasterized, restyled or discarded.

Actual ChemDraw 25.0.2.14 controls cover HTML/CSS scripts, normal/bold Arial and
7/12/16 pt source sizes. Independent native SVG measurements of 24 script runs
show maximum origin/baseline error 0.0349 pt and size error 0.0232 pt across all
54 runs. These are measured precision/font-engine differences, not a relaxation
of any consumer-reference guard. Separate runs remain individually editable;
they are not a single flowing caption after import.

## Directional label placement

Nine native Ar controls distinguish vertical, diagonal and multiple attachments.
Vertical and multiply attached Ar labels anchor their leading A; ordinary
single diagonal attachments keep the facing terminal glyph. This changes only
presentation, with the binding requirement still deciding chemical meaning.

Terminal double-bond labels center between the two actual painted stroke axes.
The same distance calculation serves line geometry and label placement;
centered doubles have zero displacement. Relayout, movement, rotation and length
refresh all use the common positioner. Atom coordinates and document bytes are
unchanged. This addresses direction-dependent O displacement rather than moving
all labels by a constant baseline correction.

## Consumer boundaries

Preserve strict chemistry, glyph fallback, color, bond-spacing and reference
checks. Native palette truncation still requires the existing explicit recovery
of a known first save before reopening. Later lossy saves cannot be relabeled
as first saves. Native font fallback, decimal spacing and hidden definition text
normalization remain separately reported limits. Generic ARY preservation is
not proof of a concrete phenyl formula or CIP assignment.
