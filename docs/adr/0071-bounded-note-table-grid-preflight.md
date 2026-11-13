# ADR 0071: Bounded note table grid preflight

- Status: Accepted
- Date: 2026-11-14

## Problem

Allowlisted note table tags let Qt build a full rows×columns grid, including
occupied colspan and rowspan slots and ragged row widths. A note within the
existing HTML byte cap can still expand into millions of cells, hanging open or
exhausting memory. The prior sanitizer stripped table structure entirely, so
keeping tables without a layout bound introduced a new resource risk.

## Decision

After the allowlisted HTML sanitizer runs, count the aggregate logical table
grid slots Qt would allocate per note, including nested tables, spanning cells
and ragged grids, with a pure-Python scanner that cannot undercount duplicate or
malformed span attributes, orphan cells, or unclosed table fragments. When the
count exceeds `MAX_NOTE_TABLE_CELLS` (10,000), re-sanitize the input with table
structural tags removed so cell text and safe inline or paragraph formatting
remain, matching the prior flattening behavior. Normal bounded tables, headings
and pre blocks are unchanged. Strict native CDXML export continues to refuse
tables. Oversized table layout is explicitly outside supported table formatting.

## Verification and limits

`test_note_html_sanitizer.py` covers at, below and above the grid budget,
colspan and rowspan occupancy, ragged and nested tables, malformed and duplicate
span attributes, text retention, and idempotency. `test_note_rich_text_persistence.py`
covers structural signatures across commit, snapshot, file reopen and copy for
bounded tables and verifies save/reopen completes for an oversized grid fixture
without retaining table frames. Offscreen Qt checks confirm behavior; they do
not replace native canvas confirmation for note editing workflows.
