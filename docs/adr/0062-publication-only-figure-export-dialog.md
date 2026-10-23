# ADR 0062: Publication-only figure export dialog

- Status: Partly superseded by ADR 0063
- Date: 2026-10-23

## Problem

CDXML is already the working-document format (ADR 0059). Offering it again in
Figure Export duplicates the desktop save workflow. Long inline explanations and
collapsed size constraints make the export options harder to scan.

## Decision

Desktop Figure Export offers SVG, PDF, PNG and TIFF. Remove its CDXML format and
reviewed-label binding controls. Save and Save As continue to write CDXML working
documents. Existing CLI CDXML conversion and shared serialization remain separate
supported paths. No documents or persistent data require migration.

Show width, maximum height and minimum font size directly, without an advanced
section or lengthy inline explanations. Retain the optional editable SVG control,
preview and actual output dimensions. A previously selected desktop CDXML export
format resolves to the first available format, SVG.

## Verification and limits

Dialog tests cover the exact four-format list, previous-format recovery, visible
limits, invalid selections and editable SVG availability. The repository gate is
`make check`; a native macOS run checks the actual layout and controls. CLI CDXML
and native-document tests continue to cover their separate supported paths.
