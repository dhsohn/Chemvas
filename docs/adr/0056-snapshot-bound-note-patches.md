# ADR 0056: Snapshot-bound note patches

- Status: Accepted
- Date: 2026-10-13
- Extends: [ADR 0010](0010-document-owned-notes-and-marks.md)

## Problem

Graph Patch v1 can edit atoms and bonds, but has no note operation. Automating a
caption correction requires rebuilding the document or modifying saved JSON
outside the checked patch boundary. Saved notes have an ordered collection;
the runtime identities described in ADR 0010 do not enter the file format.

## Decision

Extend Graph Patch v1 with `add_note`, `move_note` and `update_note`. Inspection
exposes the saved notes with zero-based `note_index`, `note_count` and
`next_note_index`. These indices identify only the exact source snapshot already
bound by the patch's SHA-256. Additions append at the next index; existing note
order and group references do not change. No persistent ID or document schema
change is needed.

`move_note` preserves saved content, HTML and rotation exactly. `update_note`
explicitly replaces all content and style using plain text or rich runs and an
optional base style; omitted styles use composition defaults. Geometry and group
references are preserved. This contract avoids interpreting a partial formatting
request as permission to flatten or merge existing rich HTML.

The Qt-free patch feature reuses the public composition service for note
validation and canonical rich-text serialization. It does not introduce a second
HTML parser. The complete candidate still passes the normal document validation
and output limits, including on a dry run. The CLI writes a new document and
does not mutate an open desktop history. Subsequent desktop editing uses the
existing document-owned notes and native text/history behavior.

## Verification and limits

`test_document_patch_notes.py` covers indices, append ordering, strict fields,
non-finite input, rich runs, unchanged graph/annotations/groups, and exact source
binding. `test_document_patch_cli.py` covers inspection, dry runs and writes.
`test_document_patch_note_workflow.py` opens a real CLI output in the editor,
checks native character formatting, edits with key input, exercises text and
committed Undo/Redo, and saves/reopens the result. It runs serially on the native
macOS or Windows backend through `scripts/check.sh`.

The contract does not provide note deletion, persistent note IDs, raw HTML input
or partial formatting merges. A changed source must be inspected again.
