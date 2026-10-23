# ADR 0063: Retire editable SVG

- Status: Accepted
- Date: 2026-10-23
- Supersedes: editable SVG portion of [ADR 0062](0062-publication-only-figure-export-dialog.md)

## Problem

CDXML is the working-document format. The optional editable SVG feature duplicates
that role by embedding document state in figure output and reopening that state.
The feature is unused in the intended workflow and has been explicitly retired.

## Decision

Remove the editable SVG checkbox, option plumbing, metadata writer and reader,
SVG document opening, and format-specific tests. SVG remains a plain publication
output. CDXML owns editable documents; MOL remains an import format.
Remove the export post-render hook whose only production caller embedded SVG
editing metadata. Ordinary SVG output continues to use atomic export.

Existing SVG files are not modified, but this release no longer opens their
embedded editing state. An older release can open such a file and save its
working document as CDXML before updating. No automatic conversion is provided.

## Verification and limits

Run `make check`, including plain SVG export, CDXML document round trips and
non-mutating SVG-open rejection. Inspect the native export dialog and export a
plain SVG, checking that it contains drawing geometry without editing metadata.
Historical ADRs and release notes retain their original feature descriptions.
