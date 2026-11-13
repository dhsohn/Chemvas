# ADR 0071: Bounded note table grid preflight

- Status: Accepted
- Date: 2026-11-14

## Problem

Allowlisted note table tags let Qt build a full rows×columns grid, including
occupied colspan and rowspan slots and ragged row widths. A note within the
existing HTML character cap can still expand into millions of cells, hanging open or
exhausting memory. The prior sanitizer stripped table structure entirely, so
keeping tables without a layout bound introduced a new resource risk.

## Decision

After the allowlisted HTML sanitizer runs, count the aggregate logical table
grid slots Qt would allocate per note for strictly nested table markup, including
nested tables, spanning cells, and ragged grids inside valid `table` › `tr` ›
`td`/`th` structure. The pure-Python scanner mirrors Qt column-skip span
placement and updates the running slot total incrementally so deeply nested
tables do not rescan every open grid on each tag.

When the count exceeds `MAX_NOTE_TABLE_CELLS` (10,000), or when markup is
ambiguous for Qt (orphan rows or cells, cells not directly inside a row, implicit
or mismatched closing, nested `p`, or `li` directly inside `li`), re-sanitize the
input with table structural tags removed so cell text and safe inline or
paragraph formatting remain, matching the prior flattening behavior. HTML that
relies on omitted end tags (for example chained `<td>` without `</td>`) is treated
as ambiguous and flattened; Chemvas and Qt saved output close tags, but this
guard is not a general HTML5 parser.

The guard applies to stored and loaded sanitized HTML on the persistence path, not
to live paste or drop, which still reach Qt before `sanitize_note_html`. Normal
bounded tables Qt exports, including merged, nested, and list-in-cell layouts,
are unchanged. Strict native CDXML export continues to refuse tables.
Oversized or ambiguous table layout is explicitly outside supported table
formatting.

## Verification and limits

`test_note_html_sanitizer.py` covers at, below and above the grid budget (including
exactly one slot over the limit), colspan and rowspan occupancy, ragged and
nested tables, overlapping spans, orphan and implicitly closed fragments,
malformed structure, duplicate span attributes on sanitizer output, text
retention, and idempotency. `test_note_rich_text_persistence.py` covers
structural signatures across commit, snapshot, file reopen and copy for
bounded tables and verifies save/reopen completes for an oversized grid fixture
without retaining table frames. Offscreen Qt checks confirm behavior; they do
not replace native canvas confirmation for note editing workflows.
