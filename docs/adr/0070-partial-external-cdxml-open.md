# ADR 0070: Partial open of external CDXML

- Status: Accepted
- Date: 2026-11-13

## Decision

Desktop open warns once when a CDXML document has no valid Chemvas editing
snapshot. If a file contains standalone headless legacy arcs that Chemvas
cannot draw, Open and Cancel are offered before a canvas changes. Only
well-formed leaf arcs under the page or its drawing groups, with understood
attributes and no object references, can be omitted. The remaining native
XML, structures and supported graphics follow the existing preserving
importer. Malformed files and unsupported chemical features still fail
validation. Headless readers keep the strict default.

A partial import opens as a separate unsaved drawing. The original path is
kept in the draft's local session metadata and restored during recovery.
Save suggests a copy name and the first successful save can only create a
new file. Source protection stays active while the copy is open and for
unsaved work recovered from that session. The saved copy carries the
ordinary Chemvas snapshot and reopens as a separate document. Local source
paths are absent from CDXML. Older builds can read ordinary session manifests
and leave a session with partial drafts for a build that understands them.

## Verification

Test cancellation, retained chemistry, malformed or referenced arcs, and
normal opening of a saved copy. Test rejection of the source and its aliases,
new file creation, and source protection after session recovery.
