# ADR 0010: Document-owned notes and marks

- Status: Accepted
- Date: 2026-09-24
- Extends: [ADR 0009](0009-document-owned-ring-fills.md)

## Problem

Notes and charge/radical marks were the remaining annotation families whose
saved values and order belonged to Qt objects. Missing views could remove saved
annotations. Mark copying and electronic-state reconciliation also depended on
the view registry, although those operations need document data.

## Decision

Store immutable `Note` and `Mark` values in `AnnotationCollection`, using the same
membership, ordering and detached-record lifetime rules as the other six kinds.
The scene keeps ID-to-view dictionaries. Runtime IDs do not enter the file format.
Keep native text editing, its cursor, focus and text Undo in Qt. Text and formatting
changes publish sanitized HTML and plain text to the note record; position and
rotation changes publish geometry. Explicit text replacement also publishes when
document signals are blocked during recovery. Saving reads only these records.

Keep the native dot, text and circled mark graphics, sharing a record binding.
Mark metadata roles are derived from their immutable record. Position changes
publish the exact rendered center, retaining existing float behavior and the
separate exact-position witness used by history. Records own kind, custom text,
atom binding, offsets, center and optional color. The view registry indexes
projections for editing; it no longer owns chemistry or clipboard membership.

The GUI and headless materializers create the same bound items. Existing atomic
transactions capture document collections and native frames. Native frame restore
can emit intermediate text/position values; the captured document record is the
final authority after a complete frame restore. Verification still checks the
native frame and container identities, and persistent failures remain failures.

No new service hierarchy, compatibility adoption path, history stack or schema
version is introduced. Document version 8 and composition schema 1 are unchanged.

## Consequences and verification

All eight annotation families now own their saved values and order outside Qt.
This closes annotation ownership, not the entire editor redesign. The subsequent
[ADR 0011](0011-document-identities-for-groups-and-history.md) migrates group and
history references to IDs, adds projection recreation during replay, and removes
the history forwarding facades. Other editor forwarding layers remain separate work.

Tests cover missing/deleted/released views, document order and group indices,
native rich text Undo and blocked signals, mark copying and electronic state,
delete/replay, failed publication, exact font/position rollback and reset. The
verification includes serial native Cocoa workflows, baseline/current saved
documents and raster comparisons, protected-code checks and the full local gate.
