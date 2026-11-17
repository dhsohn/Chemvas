# ADR 0074: Preserve detached native caption layout

- Status: Accepted
- Date: 2026-11-17

## Problem

Native captions use source-derived baseline anchors and a high-resolution Qt
layout device to retain fractional point sizes. Whole-note clipboard payloads
previously carried only HTML and ordinary note position/rotation. Pasting an
8.5-point native caption therefore rendered an 11-pixel ordinary note, and lost
the source anchor and rotation. `tests/test_cdxml_font_stroke_review.py`
reproduces this through the clipboard controller.

## Decision

The clipboard boundary carries a detached caption's baseline offset,
justification and source rotation as an optional `native_caption` note value.
The existing immutable `Note` record owns it after paste; the document and
clipboard validators accept only a four-value placement with finite coordinates
and rotation and a recognized justification. Note HTML retains fractional point
sizes and carries its source font defaults across document boundaries.

Materialization and history reconstruction use the same native layout installer
as retained-source captions. Snapshot saving preserves the note value. Adding
the copied caption to retained CDXML writes its actual baseline and rotation.
Original captions continue deriving placement from their retained source;
copying does not change them or the original XML. Legacy pixel HTML keeps its
existing layout mode. This adds no arbitrary transform or executable markup.

## Verification and limits

Focused clipboard tests cover same-document, other native-document and new
document destinations; different font defaults; mixed faces and fractional
sizes; Undo/Redo, destroyed-view reconstruction, text edits and disk reopening.
Native reimport checks cover the added caption's baseline and rotation without
the editing snapshot. Invalid placement values are refused. Old snapshots
without the optional value remain valid; older app versions may refuse the new
clipboard value. Native Cocoa interaction and the full platform gate remain
separate acceptance checks.