# ADR 0043: Preserve formal charge independently of visible atom labels

- Status: Proposed
- Date: 2026-10-11

## Reproduced defect

ChemDraw 25.0.2.14 uses a contained Text object to interpret an atomic Node,
ignoring conflicting chemical properties. A plain P label plus Charge=1 and a
separate + objecttag becomes neutral on save; O / Charge=-1 behaves likewise.
The prior OMe export loses four P+ and four O- charges. This predates ADR 0042.
InterpretChemically=yes, omitting that attribute, NeedsClean=no and explicit
NumHydrogens=0 do not restore the missing charge. Inline P+/O- or no label preserves
charge, but changes the original visible charge-marker arrangement.

## Decision

For a charged atomic node that has a visible label, retain its original outer
label, coordinates, attached mark, and all outer bonds. Encode it as a Fragment
node with one inner canonical atomic definition and a charge-bearing label.
Each incident outer bond gets a distinct ExternalConnectionPoint at the original
neighbor position. Copy its order to the inner bond. For multiple connections,
outer BondOrdering and inner ConnectionOrder declare the correspondence. Outer
B/E order, wedge/hash direction, dotted status, geometry and colors stay intact.
The original model is not edited. A charged node without a visible label already
uses native atomic properties and does not need this definition.

These are native chemical definitions, not hidden-bond drawing substitutes or
warning suppression. The inner label uses the typed element identity (e.g. H,
not an attached identifier letter) and superscript charge magnitude/sign. It
adds no chemical atoms after the fragment is expanded. Formal charges remain
explicit. No valence repair or reinterpretation of chemical dotted bonds occurs.

## Bounded evidence

The complete OMe product export retains all eight charges after actual native
save/reopen. ChemDraw's own MOL export has 288 atoms / 286 bonds, matching the
old native output's expanded graph. Unique same-element coordinate matching
(maximum difference 0.001221 MOL units; all second-nearest distances >0.1)
finds exactly four P 0→+1 and four O 0→-1 changes, no other atom fields, and no
bond order or stereo differences (15 wedge, 15 hash). The baseline's eight
neutral values are the defect; the corrected values match source annotations.

A query cannot establish a unique formula; source TS-like chemical bonds may
produce valence warnings. These warnings remain visible and are not accepted by
the strict reference validator. This ADR does not approve raw native OMe as a
layout reference or claim visual equivalence, GUI editability acceptance, or all
possible charged-element consumer behavior. Ordinary editing/PNG/PDF paths are
unchanged.

## Primary sources

- Node reading behavior: https://iupac.github.io/IUPAC-FAIRSpec/cdx_sdk/Node.htm
- Atomic charge (absence means neutral): https://iupac.github.io/IUPAC-FAIRSpec/cdx_sdk/properties/Atom_Charge.htm
- Outer bond mapping: https://iupac.github.io/IUPAC-FAIRSpec/cdx_sdk/properties/Atom_BondOrdering.htm
- Inner attachment mapping: https://iupac.github.io/IUPAC-FAIRSpec/cdx_sdk/properties/Frag_ConnectionOrder.htm
