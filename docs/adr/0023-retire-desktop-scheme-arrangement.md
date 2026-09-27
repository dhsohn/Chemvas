# ADR 0023: Retire desktop scheme arrangement

- Status: Accepted
- Date: 2026-09-28

## Problem

The desktop Arrange Scheme dialog duplicated the headless layout request surface:
users had to assign groups, caption roles and row connectors again each time.
Maintaining this unused desktop workflow required separate menu, dialog, history
and walkthrough coverage.

## Decision

Remove the desktop dialog, menu entry, GUI-only tests and walkthrough assets.
Keep `layout-document` and its measured layout implementation, which have existing
research figure generation consumers. The public CLI syntax remains supported,
including the explicit connectors in [ADR 0022](0022-explicit-reaction-layout-connectors.md).
Do not leave a hidden action, disabled menu entry or compatibility wrapper.

No persisted document format changes. Existing drawings retain their coordinates,
notes, groups and arrows and remain editable. Manual alignment, distribution and
grouping remain available. Automated users continue through the documented CLI.

## Verification and limits

Menu assembly and image workflow tests verify the retained desktop actions.
CLI tests verify layout, reopen and export. Repository searches check removed
symbols and walkthrough references; `make check` covers the integrated change.
A native menu inspection confirms the entry is absent. Installation and release
are separate operations; this patch does not update installed applications.
