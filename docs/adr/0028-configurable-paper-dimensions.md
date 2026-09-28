# ADR 0028: Configurable paper dimensions

- Status: Accepted
- Date: 2026-09-28

## Context

A4-only validation and rendering cause large authored drawings to exceed the
sheet. A background shape does not change the document's editable paper bounds.

## Decision

Keep paper presets and custom-dimension validation in the Qt-free document
package. Retain A4's exact 595 × 842 coordinate dimensions. Add A0–A5, Letter,
Legal and Tabloid, plus Custom dimensions in mm bounded to 10–2000 per side.
Custom dimensions specify actual width and height; orientation applies only to
presets. Desktop and headless scene construction consume the same dimensions.
Paper resizing preserves drawing coordinates, participates in existing sheet
transactions and Undo/Redo, and persists through the document settings owner.

Write document v9, schema 1, with minimum reader 0.23.0. Existing v7/v8 readers
reject the expanded enum/optional field, so the new generation makes that
boundary explicit. Continue reading valid v7/v8 without modifying source files.
Reject new paper settings disguised as older formats. Default A4 behavior remains.

## Verification

Cover standard/custom dimensions, invalid and non-finite input, legacy formats,
GUI editing/cancellation, history rollback, save/reopen and headless scene bounds.
