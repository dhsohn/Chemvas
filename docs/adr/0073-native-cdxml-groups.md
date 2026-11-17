# ADR 0073: Native CDXML groups

- Status: Accepted
- Date: 2026-11-17
- Extends: [ADR 0058](0058-desktop-cdxml-documents.md),
  [ADR 0067](0067-coupled-native-cdxml-collections.md)

## Problem

Preserving import kept ChemDraw `<group>` elements only inside the
`cdxml_source` XML. Editor `state["groups"]` stayed empty, so moving one
imported member did not move the others, even when ChemDraw had grouped them.

## Decision

Qt-free `features/cdxml_native_groups.py` owns the import mapping and the
save-time sync. `PreservingImporter.state()` and the native writer call it.
The persisted `cdxml_source` schema and its strict validation do not change:
no field records which native groups were mapped.

**Import.** A native `<group>` is mapped when all of these hold:

- it is a direct child of the page;
- it contains no nested `<group>`;
- every visible descendant was imported as a bound record (top-level `<n>`
  atoms through the node order, and notes, images, arrows and shapes through
  item bindings);
- it has at least two members;
- none of its members is already in an earlier mapped group.

Each mapped group becomes one editor group with exactly those atoms and
`[collection, index]` items. `state["groups"]` is set before the baseline
deepcopy, so `source["baseline"]` holds the same groups.

**Which groups import mapped.** Save recomputes the import mapping from the
immutable `source["xml"]`: it uses the importer's top-level node order and
`source["baseline_items"]`. A recomputed group counts as mapped only when
`source["baseline"]["groups"]` contains the same editor group. Save never
judges eligibility from the XML it is writing. A group that an earlier save
step changed, for example by detaching a `<chemicalproperty>`, therefore
stays as it was. Snapshots written before groups were mapped have no
baseline groups, so their native groups stay XML-only.

**Save.** A mapped group's remaining members are its imported native member
IDs that are still bound in the live state. Save does nothing to the group
when fewer than two members remain, or when some current editor group
contains all of them. Editor members are translated to native IDs through
`source["atoms"]` and the live `source["items"]`. Otherwise save unwraps the
group: its children move into the page at the group's position in order, and
the `<group>` element is removed.

- **Group attributes.** Chemvas resolves some attributes through every
  ancestor: `color`, `bgcolor`, `Visible`, `LineWidth`, `BoldWidth`,
  `MarginWidth`, `BondSpacing`, `BondSpacingAbs`, `Justification`,
  `CaptionJustification` and `LabelJustification`. Save copies the group's
  value for each of these onto every direct child that does not set the key.
  Every descendant then resolves the same value as before, and child and
  descendant overrides still win. `id`, `BoundingBox` and `Z` describe only
  the group and are dropped with it.
- **Refusals.** Unwrapping refuses the save in two cases: the group has any
  other attribute (for example `Integral` or `fgcolor`), or the group has a
  direct `<objecttag>` or `<annotation>` child. Neither can be carried to the
  children without changing what it means.
- **References.** The unwrapped group's ID counts as removed for the
  writer's existing checks. A `<chemicalproperty>` whose `BasisObjects`
  names the group is detached, and its caption stays as plain text. Any
  other native reference to the group refuses the save. This includes
  reaction-step arrow and above/below lists, which are pruned for deleted
  objects but not for unwrapped groups, because the group's members still
  exist.

A refusal raises before anything is written, so the existing file and the
editor state stay unchanged.

Save does not write new Chemvas groups among native objects, or members added
to a mapped group, into native `<group>` XML. Those relationships persist only
in the embedded Chemvas snapshot.

## Consequences

- A page-level ChemDraw group of, for example, a molecule and a caption opens
  as one editor group and moves together.
- Nested groups, groups containing an object Chemvas did not bind, and groups
  in snapshots from earlier versions create no editor group. Their XML is
  preserved as before.
- An untouched save writes a mapped group back unchanged. Expanding an
  imported group keeps the native `<group>` with its original children.
- Splitting or ungrouping, so that no editor group holds every remaining
  member, unwraps the group. Reopening the native XML alone then yields no
  editor group. Reopening the embedded snapshot keeps the source XML, so
  every later save unwraps the group again.
- Ungrouping a native group with unsupported attributes, metadata children
  or native references to its ID fails the save until the members are
  grouped again.

## Verification and limits

`tests/test_cdxml_native_groups.py` covers:

- import and co-movement of a molecule and caption, and molecule and shape
  groups;
- nested and unimportable groups;
- the unchanged `cdxml_source` field set and its strict validation;
- ungroup unwrap and native-only reopen;
- an untouched save that leaves the XML unchanged;
- wrapper retention after deleting one member, and unwrap after deleting a
  member and ungrouping;
- the save sync keeping an expanded group and unwrapping a split one;
- inherited colour from `tests/fixtures/cdxml-interop-colors.cdxml`, and
  inherited style with child overrides and no copied `BoundingBox`/`Z`;
- hidden captions staying hidden;
- refusal of unsupported attributes and metadata, with unchanged state and
  an unchanged file on disk;
- refusal of step reactant and above-arrow references, and detaching a
  chemical property based on the group;
- snapshots from earlier versions;
- groups the save step changed staying unmapped.

Limits:

- Only page-level, non-nested groups map.
- Save never adds native `<group>` elements or children.
- The inherited-attribute list follows what Chemvas itself resolves through
  ancestors, not the full ChemDraw specification. Other group attributes are
  refused rather than guessed.
- Reaction-step references to a group block ungrouping; save does not
  rewrite them to the members.
