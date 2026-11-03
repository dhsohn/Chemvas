"""Map page-level native ChemDraw ``<group>`` elements to editor groups.

Import creates ``state["groups"]`` entries for qualifying native groups so
members move together. Save keeps a native ``<group>`` when some editor group
contains every mapped native member (superset or equal) and unwraps only when
none does. New Chemvas groups and added members are not written into the native
``<group>`` XML; they remain in the embedded Chemvas snapshot.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import xml.etree.ElementTree as ET
    from collections.abc import Mapping

# Tags that may sit under a native group without being editor members.
_STRUCTURAL_TAGS = frozenset(
    {"fragment", "b", "s", "represent", "objecttag", "annotation"}
)
_PROJECTED_ITEM_TAGS = frozenset(
    {"t", "embeddedobject", "graphic", "arrow", "curve", "ColoredMolecularArea"}
)
_ITEM_COLLECTIONS = (
    "notes",
    "images",
    "arrows",
    "shapes",
    "marks",
    "orbitals",
    "ts_brackets",
)


def _has_ancestor(
    element: ET.Element, tag: str, parents: dict[ET.Element, ET.Element]
) -> bool:
    current = parents.get(element)
    while current is not None:
        if current.tag == tag:
            return True
        current = parents.get(current)
    return False


def _is_under(
    element: ET.Element, ancestor: ET.Element, parents: dict[ET.Element, ET.Element]
) -> bool:
    current = parents.get(element)
    while current is not None:
        if current is ancestor:
            return True
        current = parents.get(current)
    return False


def _inherited(
    element: ET.Element,
    key: str,
    default: str,
    parents: dict[ET.Element, ET.Element],
) -> str:
    current: ET.Element | None = element
    while current is not None:
        if key in current.attrib:
            return current.attrib[key]
        current = parents.get(current)
    return default


def _nested_group(group: ET.Element) -> bool:
    return any(child is not group for child in group.iter("group"))


def _visible_item_element(
    element: ET.Element,
    parents: dict[ET.Element, ET.Element],
) -> bool:
    if element.tag == "t":
        if _has_ancestor(element, "n", parents):
            return False
        return _inherited(element, "Visible", "yes", parents) != "no"
    if element.tag == "embeddedobject":
        return True
    if element.tag in {"graphic", "arrow", "curve", "ColoredMolecularArea"}:
        return not element.get("SupersededBy")
    return False


def _mapped_members(
    group: ET.Element,
    *,
    parents: dict[ET.Element, ET.Element],
    node_ids: Mapping[str, int],
    bindings: Mapping[str, list[str | None]],
    by_id: Mapping[str | None, ET.Element],
) -> dict[str, Any] | None:
    """Editor group record for ``group``, or None when it must stay XML-only."""
    if _nested_group(group):
        return None

    atoms: list[int] = []
    claimed: set[ET.Element] = set()
    for atom_native_id, atom_index in node_ids.items():
        element = by_id.get(atom_native_id)
        if element is None or not _is_under(element, group, parents):
            continue
        atoms.append(atom_index)
        claimed.add(element)
    atoms.sort()

    items: list[list[str | int]] = []
    for collection in _ITEM_COLLECTIONS:
        for index, item_native_id in enumerate(bindings.get(collection, [])):
            if item_native_id is None:
                continue
            element = by_id.get(item_native_id)
            if element is None or not _is_under(element, group, parents):
                continue
            items.append([collection, index])
            claimed.add(element)

    for element in group.iter():
        if element is group:
            continue
        if element.tag in _STRUCTURAL_TAGS:
            continue
        if element.tag == "n":
            if _has_ancestor(element, "n", parents):
                continue
            if element not in claimed:
                return None
            continue
        if element.tag in _PROJECTED_ITEM_TAGS:
            if not _visible_item_element(element, parents):
                continue
            if element not in claimed:
                return None
            continue
        return None

    if len(atoms) + len(items) < 2:
        return None
    return {"atoms": atoms, "items": items}


def editor_groups_from_native(
    page: ET.Element,
    *,
    parents: dict[ET.Element, ET.Element],
    node_ids: Mapping[str, int],
    bindings: Mapping[str, list[str | None]],
    by_id: Mapping[str | None, ET.Element],
) -> list[dict[str, Any]]:
    """Build disjoint editor groups for qualifying page-level native groups."""
    groups: list[dict[str, Any]] = []
    seen_atoms: set[int] = set()
    seen_items: set[tuple[str, int]] = set()
    for child in list(page):
        if child.tag != "group":
            continue
        mapped = _mapped_members(
            child,
            parents=parents,
            node_ids=node_ids,
            bindings=bindings,
            by_id=by_id,
        )
        if mapped is None:
            continue
        atom_ids = mapped["atoms"]
        item_refs = [(str(kind), int(index)) for kind, index in mapped["items"]]
        if seen_atoms.intersection(atom_ids) or seen_items.intersection(item_refs):
            continue
        seen_atoms.update(atom_ids)
        seen_items.update(item_refs)
        groups.append(
            {
                "atoms": list(atom_ids),
                "items": [[kind, index] for kind, index in item_refs],
            }
        )
    return groups


def _native_ids_for_editor_group(
    group: dict[str, Any],
    *,
    atom_native: Mapping[str, str],
    items: Mapping[str, list[str | None]],
) -> frozenset[str]:
    native_ids: set[str] = set()
    for atom_id in group.get("atoms", []):
        native = atom_native.get(str(atom_id))
        if native is not None:
            native_ids.add(native)
    for reference in group.get("items", []):
        if not isinstance(reference, (list, tuple)) or len(reference) != 2:
            continue
        kind, index = reference
        bindings = items.get(str(kind), [])
        if isinstance(index, int) and 0 <= index < len(bindings):
            native = bindings[index]
            if native is not None:
                native_ids.add(native)
    return frozenset(native_ids)


def _native_ids_for_mapped_group(
    group: ET.Element,
    *,
    parents: dict[ET.Element, ET.Element],
    node_ids: Mapping[str, int],
    bindings: Mapping[str, list[str | None]],
    by_id: Mapping[str | None, ET.Element],
    atom_native: Mapping[str, str],
) -> frozenset[str] | None:
    mapped = _mapped_members(
        group,
        parents=parents,
        node_ids=node_ids,
        bindings=bindings,
        by_id=by_id,
    )
    if mapped is None:
        return None
    return _native_ids_for_editor_group(mapped, atom_native=atom_native, items=bindings)


def _unwrap_group(
    group: ET.Element,
    parents: dict[ET.Element, ET.Element],
    by_id: dict[str | None, ET.Element],
) -> None:
    parent = parents.get(group)
    if parent is None:
        return
    children = list(group)
    index = list(parent).index(group)
    for child in children:
        group.remove(child)
    for offset, child in enumerate(children):
        parent.insert(index + offset, child)
        parents[child] = parent
    parent.remove(group)
    parents.pop(group, None)
    native_id = group.get("id")
    if native_id is not None:
        by_id.pop(native_id, None)


def sync_native_groups_on_save(
    page: ET.Element,
    *,
    parents: dict[ET.Element, ET.Element],
    by_id: dict[str | None, ET.Element],
    state: dict[str, Any],
    source: dict[str, Any],
) -> None:
    """Unwrap native groups the importer would map when no editor group covers them."""
    atom_native = {str(key): value for key, value in source.get("atoms", {}).items()}
    # Prefer live bindings; fall back to baseline for collections omitted live.
    live_items = source.get("items") or {}
    baseline_items = source.get("baseline_items") or {}
    bindings: dict[str, list[str | None]] = {}
    for collection in _ITEM_COLLECTIONS:
        if collection in live_items:
            bindings[collection] = list(live_items[collection])
        elif collection in baseline_items:
            bindings[collection] = list(baseline_items[collection])
        else:
            bindings[collection] = []

    live_atom_keys = {str(key) for key in state.get("model", {}).get("atoms", {})}
    node_ids = {
        native_id: int(atom_key)
        for atom_key, native_id in atom_native.items()
        if native_id in by_id and str(atom_key) in live_atom_keys
    }

    editor_sets = [
        _native_ids_for_editor_group(group, atom_native=atom_native, items=bindings)
        for group in state.get("groups") or []
        if isinstance(group, dict)
    ]

    for child in list(page):
        if child.tag != "group":
            continue
        native_set = _native_ids_for_mapped_group(
            child,
            parents=parents,
            node_ids=node_ids,
            bindings=bindings,
            by_id=by_id,
            atom_native=atom_native,
        )
        if native_set is None:
            continue
        # Keep when an editor group contains every mapped native member.
        if any(native_set <= editor_set for editor_set in editor_sets):
            continue
        _unwrap_group(child, parents, by_id)
