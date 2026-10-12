# ADR 0037: Bound 4-F-Ph stereo wide-end CDXML attachment

- Status: Proposed
- Date: 2026-10-06
- Extends: [ADR 0036](0036-bound-para-fluorophenyl-cdxml.md), [ADR 0035](0035-ph-stereo-nickname-attachments.md)
- Recorded: 2026-10-06

## Problem

ADR 0036 exports a fixed para-fluorophenyl graph for `CdxmlLabelBinding.
aryl_fragment("4-F-Ph")` on drawn `Ar` only through one ordinary single
external bond. ADR 0035 allows unbound `Ph` on the wide end of order-1 wedge or
hash bonds. Inventory figures pair `Ar` (explicit `4-F-Ph` binding) with a
stereo hash at a wide `bond.b` and an unbound elemental narrow `bond.a` (for
example phosphorus at atom 6, bond ordinal 11). The exporter refused every
wedge/hash attachment for bound `Ar`, including this case.

## Decision

1. **Narrow exception.** When the drawn label is exactly `Ar`, the validated
   binding is `aryl_fragment("4-F-Ph")` only, and the sole attachment is one
   order-1 wedge or hash bond with `Ar` at `bond.b`, apply the same outer stereo
   encoding as unbound wide-end `Ph`: native `B`/`E`, `WedgeBegin` or
   `WedgedHashBegin`, and the existing rendered narrow-at-`bond.a` check.
   `bond.a` must be an unbound supported pure element (`_require_supported_element_neighbor`
   with full `label_bindings` context so typed narrow centres refuse).

2. **Unchanged inner graph and guards.** The `4-F-Ph` nickname graph, plain-single
   attachment for the same binding, unbound `Ph` stereo rules, generic/`Ph`
  /`unknown` aryl bindings on stereo bonds, charge/radical, attachment count,
   interleaving, Z-order, and bond encoding paths are unchanged except for this
   eligibility branch in `_group_label_attachment`.

3. **Producer-only.** Native CDXML bytes are emitted from fixed internal
   definitions; ChemDraw visual display, chemical interpretation, and roundtrip
   success are not claimed.

## Verification

- `tests/test_cdxml_bound_fluorophenyl_stereo.py` including synthetic atom
  6/11/bond 11 regression with phosphorus at the narrow centre.
- `tests/test_cdxml_bound_fluorophenyl.py` stereo wide-end and refusal matrix
  updates.
- Owner serial Qt/CLI gates; real multi-figure inventory export is not claimed.

## Consequences

Export-only change in `export_cdxml.py`. No public API, document schema, sidecar
parser, or CLI changes beyond existing `aryl_fragment` documentation.
