# ADR 0035: CDXML Ph stereo nickname attachments

- Status: Proposed
- Date: 2026-10-06
- Extends: [ADR 0030](0030-cdxml-export.md)
- Recorded: 2026-10-06

## Problem

ADR 0030 decision 17 exports verified group labels `Me`, `Ph`, and `tBu` only
when exactly one plain single bond attaches the nickname. Chemvas also draws
order-1 wedge and hash bonds whose narrow end is `bond.a` and whose wide end is
`bond.b`. A phenyl substituent drawn as the literal unbound label `Ph` on the
wide end of such a bond is a common editorial pattern, but the exporter refused
every wedge or hash attachment, including `Ph` at `bond.b` with an elemental
stereocentre at `bond.a`. Tests in `tests/test_cdxml_export.py` encoded that
refusal. No consumer roundtrip or ChemDraw visual proof exists for nickname
nodes on stereo bonds.

## Decision

1. **Narrow the exception to unbound `Ph` only.** In
   `app/chemvas/ui/export/export_cdxml.py`, `_group_label_attachment` (formerly
   `_single_plain_attachment`) accepts one order-1 wedge or hash attachment
   when the group label is exactly `Ph`, the label atom is `bond.b`, and
   `bond.a` is an unbound supported pure element (no typed label binding on
   that atom). The outer bond keeps native `B`/`E`, order 1, and `Display` of
   `WedgeBegin` or `WedgedHashBegin`. Existing rendered narrow-at-`bond.a`
   checks are unchanged.

2. **Keep the rest of decision 17.** `Me` and `tBu` still require a plain
   single bond. Unbound `Ph` at `bond.a`, typed label bindings on the stereo
   centre or on a wide-end `Ar` nickname, raw `Ar`, charge or radical
   annotations on the nickname, zero-length or multiple attachments, and
   neighbours that do not export as pure elements remain refused. The phenyl
   nickname inner graph, label text, and connection-point placement rules are
   unchanged.

3. **Tests.** `tests/test_cdxml_ph_stereo.py` holds positive `wide_end` cases
   and negatives; `tests/test_cdxml_export.py` replaces the former wide-end
   `Ph` hash refusal with a narrow-end `Ph` hash refusal.

4. **Documentation.** This ADR records the export contract amendment. ADR 0030
   text is not rewritten; status linkage follows when the change is accepted
   after consumer proof.

## Verification

- `tests/test_cdxml_ph_stereo.py` — synthetic export assertions for native
  stereo display, endpoint ids, nested phenyl topology, and refusals listed in
  the decision.
- `tests/test_cdxml_export.py` — retained group-label attachment refusal matrix
  with the updated `Ph` narrow-end case.
- Owner must run `bash scripts/check.sh tests/test_cdxml_ph_stereo.py` (and the
  touched export tests) on macOS or Linux with Qt offscreen; ChemDraw or other
  consumer rendering of nickname nodes on stereo bonds remains unproved.

## Consequences

Export-only behaviour in the existing CDXML owner module. No public API,
document schema, GUI, or registry changes. Follow-ups still unsupported without
their own decisions: unbound `Ph` at the narrow end, other group labels on
stereo wide ends, typed bindings on the stereo centre, and any change to
interleave or graphics flattening rules.
