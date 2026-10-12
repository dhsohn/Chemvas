# ADR 0044: Native-verified label interpretation; hydrogen normalization stays explicit

Status: Extended by [ADR 0045](0045-native-reference-semantic-normalization.md).

## Evidence and decision

The native ChemDraw 25.0.2.14 OMe witness had 88 false interpretation warnings:
12 P, 28 O, 16 H, 16 Me, 16 tBu. Changing only those exact label interpretation
flags removed all 88 without changing any atom/bond chemistry field or label text.
It exposed nine valence warnings previously masked by interpretation warnings.
Thirteen labeled-atom valence warnings, two carbon warnings and one query-formula
warning remain. None is suppressed. The original dotted bonds remain chemical.

Enable interpretation only when the exact P/O/H spelling matches the resolved
atomic number, or Me/tBu matches its verified fragment. This intentionally small
evidence boundary does not extend the correction to other elements, abbreviations,
identifier hydrogens or Ar bound to a fixed group. Existing charged Fragment and
generic ARY definitions remain unchanged. Broader interpretation needs its own
native proof, including valence and label-layout behavior.

## NumHydrogens and semantic ownership

The SDK defines omission by minimum valence requirements; the property is
meaningful only on Element nodes. The witness has 112 additions and 80 deletions,
not just 112 changes. Local graph accounting distinguishes equivalent defaults,
query bookkeeping, and source atoms whose overvalent graph prevents this inference.
No generic missing-equals-zero rule is added. The strict consumer-reference guard
is unchanged; raw native output remains unapproved.

Formal charge, element identity and original outer bond attachment belong to the
chemical model. Label spelling/layout belongs to presentation. The charged and ARY
Fragment definitions and ordered port mapping preserve that distinction for a
future importer/editor, but this change implements no import/edit UI. Normalization
evidence must not overwrite source chemistry or collapse structures into pictures.

## Sources and verification boundary

- [SDK InterpretChemically](https://iupac.github.io/IUPAC-FAIRSpec/cdx_sdk/properties/InterpretChemically.htm)
- [SDK Node](https://iupac.github.io/IUPAC-FAIRSpec/cdx_sdk/Node.htm)
- [SDK NumHydrogens](https://iupac.github.io/IUPAC-FAIRSpec/cdx_sdk/properties/Atom_NumHydrogens.htm)

The adjacent review evidence includes source/native XML, MOL chemistry-block
comparison, per-source-atom warning mapping, hydrogen classification, exact bridge
scripts and receipts. Test coverage is a selected export scope, not a full suite
or manual GUI acceptance.
