# ADR 0068: Native CDXML groups

- Status: Accepted
- Date: 2026-11-03
- Extends: [ADR 0058](0058-desktop-cdxml-documents.md),
  [ADR 0067](0067-coupled-native-cdxml-collections.md)

## Context

Preserving import kept ChemDraw `<group>` elements only inside `cdxml_source`
XML. Editor `state["groups"]` stayed empty, so moving one imported member did
not move the others even when ChemDraw had grouped them.

## Decision

Own import mapping and save-time sync in Qt-free
`features/cdxml_native_groups.py`, called from `PreservingImporter.state()` and
the native writer (same style as `cdxml_editable_rectangles`).

**Import.** For each native `<group>` that is a direct child of the page,
contains no nested `<group>`, and whose every visible descendant was imported as
a bound record (fragment atoms via the node index map; notes, images, arrows and
shapes via item bindings), create one editor group with exactly those atoms and
`[collection, index]` items when there are at least two members. Groups that
fail any condition create no editor group. Set `state["groups"]` before the
baseline deepcopy so baseline carries the same groups. Do not add a new
persisted provenance field.

**Save.** For each native `<group>` the importer would have mapped, derive its
member set as native IDs (atom IDs from `source["atoms"]`, item IDs from
`items` / `baseline_items`). Keep the native `<group>` when some current editor
group contains every mapped native member (superset or equal, after translating
editor members to native IDs through current bindings). Unwrap only when no
editor group contains all of them: move its children into the parent at the
group's position, preserving order, and remove the `<group>` element. Deleting a
member still deletes that element only; a remaining mapped membership that an
editor group still covers keeps the wrapper. Expanding an imported group in the
editor does not rewrite native children — the added members stay in the embedded
Chemvas snapshot only.

## Consequences

- A ChemDraw page-level group of a molecule and caption (or black rectangle
  shape) opens as one editor group and moves together.
- Nested groups and groups that contain an object Chemvas did not bind create
  no editor group (XML preserved as today).
- Ungrouping then saving unwraps the native `<group>`; reopening native XML
  alone yields no editor group.
- Untouched saves remain byte-identical for mapped groups an editor group still
  covers.
- Expanding an imported group keeps the native `<group>` with its original
  children; splitting or ungrouping so no editor group contains all original
  members unwraps it.
- **Not written to native XML:** new editor groups among native objects, and
  members added to a native-mapped group in Chemvas. Those relationships persist
  in the embedded Chemvas snapshot only; save does not rewrite native `<group>`
  children to include them.

## Verification and limits

`tests/test_cdxml_native_groups.py` covers molecule+caption import and
co-movement, nested and unimportable groups, ungroup unwrap and native-only
reopen, byte-identical untouched save, delete-one-member wrapper retention,
expand-keeps / split-unwraps save sync, and molecule+black-rectangle groups.
