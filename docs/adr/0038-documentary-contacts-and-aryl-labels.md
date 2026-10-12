# ADR 0038: Documentary TS contacts and unexpanded aryl labels (CDXML v2 sidecar)

- Status: Proposed
- Date: 2026-10-07
- Extends: [ADR 0030](0030-cdxml-export.md)
- Recorded: 2026-10-07

## Problem

Some inventory figures draw transition-state contacts as native order-1 dotted
bonds between a phosphorus or identifier hydrogen and an `Ar` label that is
meant as an unexpanded substituted aryl nickname, not argon, not `Ph`, and not
a bound `4-F-Ph` graph. ADR 0030 refuses all dotted bonds and treats raw `Ar`
as ambiguous unless a v1 binding selects argon, generic aryl, or a bound
fragment. There is no supported way to export the contacts as non-chemical
graphics while keeping the drawn `Ar` text and a caller-authored note.

## Decision

1. **Opt-in v2 sidecar only.** `chemvas-cdxml-label-bindings` version `2`
   keeps every v1 binding meaning and field shape. It adds:
   - `aryl_label` on drawn `Ar` only, with a non-empty `author_note` string
     (metadata; never used to infer graph topology).
   - `documentary_contacts`: a non-empty list of explicit permissions, each
     naming one native `bond_id`, endpoints `a`/`b`, `native_order` `1`,
     `native_style` `dotted`, and `classification` `ts_contact`, with optional
     `contact_id`. The sidecar remains SHA-256-bound to exact `.chemvas` bytes;
   v1 sidecars and `CDXML_LABEL_BINDINGS_VERSION = 1` behaviour are unchanged.

2. **Export-boundary authorization.** `authorize_documentary_contact_for_export`
   in `chemvas.features.export` re-validates every contact record at preflight
   and serialize time (exact `int` ids, `native_order` 1, `native_style`
   `dotted`, `classification` `ts_contact`, optional `contact_id`). Frozen
   dataclass instances constructed without the parser are not trusted.

3. **Fail-closed contact permission.** For CDXML export with a v2 sidecar, every
   exported order-1 dotted bond must appear in `documentary_contacts` with
   endpoints and native order/style matching the live document. Unlisted dotted
   bonds, stale bond slots, hidden or out-of-scope endpoints, duplicate
   `bond_id`s, and contacts without exactly one `aryl_label` `Ar` endpoint are
   refused before output. The other endpoint must export as a supported
   elemental identity (including typed identifier hydrogens via existing
   `element` bindings). Documentary edges are excluded from chemical
   `connected_atom_components` and are not emitted as `<b>`; they become page-level
   `<graphic GraphicType="Line" LineType="Dashed">` with uniform transform,
   native colour, and bond line width. `objecttag` metadata uses
   `Name` prefixed with `Chemvas.` (not reserved `CS`/`CD` prefixes),
   `TagType="String"`, `Persistent="yes"`, `Tracking="no"`, and does not
   participate in drawable `Z` assignment.

4. **Unexpanded `Ar` caption (no chemical node).** Every exported `aryl_label`
   binding (typed API or v2 sidecar) emits drawn `Ar` as a page-level `<t
   InterpretChemically="no">` (visible `Ar` text, native label
   position/font/colour), not as `<n>`, for visible atoms in the export scope.
   Chemvas `objecttag`s carry the exact `author_note` and caption metadata
   (`atom_id`, `meaning=aryl_label`, unexpanded label, no chemical atom
   identity, no automatic tracking). `documentary_contacts` remain optional for
   caption emission; the v2 JSON sidecar still requires a non-empty
   `documentary_contacts` list when that field is used. Documentary dashed
   contacts still target the original drawn Ar coordinates; permitted contacts
   remain non-chemical `<graphic>` lines only.

   **Consumer evidence (ChemDraw 25.0.2.14, owner probes, not claimed PASS):**
   both an initial `NodeType="Unspecified"` node and a follow-up
   `NodeType="GenericNickname" GenericNickname="Ar"` node were observed after
   Save As to reopen as argon (`Element="18"`, warnings, no
   NodeType/GenericNickname, note/graphics retained). That supersedes any
   assumption that a chemical node can honestly represent documentary `Ar`.

   **Fail-closed chemical degree on Ar.** If exported `aryl_label` Ar has any
   remaining non-documentary bond in the live document (single, wedge, hash, or
   multiple), including when the other endpoint is hidden or outside the export
   selection, export refuses before output. Chemvas does not drop or redraw
   those `<b>` elements, omit bonds silently, or invent a carrier carbon. v1
   `generic_aryl` / `Ph` / `4-F-Ph` paths keep their existing chemical-bond
   behaviour and guards; only `aryl_label` applies this caption boundary.

   Identifier hydrogens keep existing `element` bindings; H superscript labels
   are not converted to notes. Charge and radical annotations on the aryl label
   refuse.

5. **Producer-only claim.** This records Chemvas encoding from an explicit
   sidecar. Metadata retention in ChemDraw or any other consumer, chemical
   roundtrip, and automatic atom movement tracking are **not** verified.
   Historical SDK receipts and old documents are not retroactively validated as
   modern consumer evidence.

## Consequences

- Callers with TS dotted contacts must author v2 sidecars; v1 paths and all
  existing `generic_aryl` / `Ph` / `4-F-Ph` behaviour stay as before.
- CLI `render-document` reports `version` and `documentary_contacts` in
  `cdxml_label_bindings` when a v2 sidecar is used; v1 reports stay unchanged.
- Tests in `tests/test_cdxml_documentary_contacts.py` are synthetic fixtures
  only, not statements about real research figures.
