# ADR 0045: Native reference normalization with preserved chemical ownership

- Status: Proposed
- Date: 2026-10-11
- Extends: [ADR 0044](0044-native-known-label-interpretation.md)

## Problem

ChemDraw SaveAs renumbers nested atom-definition fragments while preserving atom
and bond IDs, owners and ordered ports. It also writes 112 NumHydrogens values and
omits 80 in the OMe witness. Literal equality rejected these representations.

Seven cases had been held because ordinary local valence inference does not
apply: source P+ 21/66, O- 28/73 and H 119/164/209. Direct comparison of all 240
source atom owners and 238 source bonds proved that the exporter preserves their
charge, order, direction and dashed/stereo display. Charged definitions also retain
each ordered external attachment. These research/TS representations are not
classified as drawing mistakes. Dotted bonds store order 1; no fractional order
exists in the source schema to infer.

An additional seven-count A/B witness, changing only absent NumHydrogens to zero,
retains identical native MOL chemistry/coordinates and the same native warnings.
These canonical labels contain no attached H count. The native zero describes the
same label; it does not repair a chemical graph or prove ordinary valence.

## Decision

Compare definition-fragment ownership using the stable owning node and its sole
definition slot. Continue to require every atom/bond ID, member ownership, graph
field and geometry. Top-level fragment IDs remain strict. Duplicate object IDs,
multiple definitions per owner, moved members and changed port order fail closed.
BondOrdering and ConnectionOrder are now explicitly compared.

Allow missing versus explicit NumHydrogens only when both nodes independently
match a witnessed representation: unlabeled neutral C with bond sum 1/4 gives
3/0; exact chemically interpreted P/O/H and P+/O- labels have zero attached H for
the witnessed bond sums; GenericNickname ARY zero is bookkeeping. Unknown node
properties, isotope/radical/query contexts, unsupported elements or bond sums,
fractional/triple orders, changed explicit counts and identifier labels fail closed.
No XML/model is rewritten by validation; no general valence engine is introduced.

The seven exceptional TS counts require more than an equal bond-order sum. H
must have two order-1 Dash bonds in a page-level fragment. Five-coordinate P+
and two-coordinate O- must be the sole chemical atom in their charged Fragment
definition, with respectively five or two ordinary order-1 external-port bonds,
complete unique ConnectionOrder/BondOrdering membership and the witnessed outer
order-1 display/direction pattern. P+ has two Solid, WedgeBegin, WedgedHashBegin
and Dash bonds beginning at the owner; O- has one outgoing Solid and one incoming
Dash. Equal-sum double-bond alternatives and other display/definition contexts
are rejected on both sides of the comparison. This conservative recognition does
not infer validity for a new graph and does not change the other ordinary forms.

## Verification and limits

The actual witness has 88 renumbered nested definitions, 480 retained nodes, 390
retained bonds, 192 supported H attribute changes and unchanged ordered ports.
Synthetic overlays isolate these native changes through the public validator;
adversarial tests change membership, IDs, ports, chemistry, counts and context.
Whole-file related tests run in separate processes. The raw native document still
fails other graphic/text checks and is not an approved layout reference.

The original source chemistry and visible output remain unchanged. Generic Ar and
charged definitions retain their distinct chemical and presentation ownership for
a later importer; this change adds no importer/editor UI.

Sources: [Node SDK](https://iupac.github.io/IUPAC-FAIRSpec/cdx_sdk/Node.htm),
[NumHydrogens SDK](https://iupac.github.io/IUPAC-FAIRSpec/cdx_sdk/properties/Atom_NumHydrogens.htm),
[Fragment SDK](https://iupac.github.io/IUPAC-FAIRSpec/cdx_sdk/Fragment.htm).
