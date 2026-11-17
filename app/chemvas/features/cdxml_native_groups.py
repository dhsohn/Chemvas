"""Map page-level native ChemDraw ``<group>`` elements to editor groups.

Import creates ``state["groups"]`` entries for qualifying native groups so
members move together. Save derives which native groups import mapped from the
immutable ``cdxml_source`` XML and its baseline, keeps a mapped ``<group>`` while
some editor group contains every remaining mapped member, and otherwise unwraps
it. New Chemvas groups and added members are not written into native
``<group>`` XML; they remain in the embedded Chemvas snapshot.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from chemvas.domain.document.cdxml_source import parse_native_xml

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
_ITEM_COLLECTIONS = ("notes", "images", "arrows", "shapes")
# Attributes Chemvas resolves through every ancestor, a group included. Moving
# a group's value onto each direct child that does not set the key keeps the
# value every descendant resolves; child and descendant overrides still win.
INHERITED_STYLE_KEYS = frozenset(
    {
        "color",
        "bgcolor",
        "Visible",
        "LineWidth",
        "BoldWidth",
        "MarginWidth",
        "BondSpacing",
        "BondSpacingAbs",
        "Justification",
        "CaptionJustification",
        "LabelJustification",
    }
)
# Attributes describing only the group element; they go with it on unwrap.
_GROUP_OWN_KEYS = frozenset({"id", "BoundingBox", "Z"})
# Direct children annotating the group itself; they cannot move to its parent.
_GROUP_METADATA_TAGS = frozenset({"objecttag", "annotation"})


def _has_ancestor(
    element: ET.Element, tag: str, parents: Mapping[ET.Element, ET.Element]
) -> bool:
    current = parents.get(element)
    while current is not None:
        if current.tag == tag:
            return True
        current = parents.get(current)
    return False


def _is_under(
    element: ET.Element,
    ancestor: ET.Element,
    parents: Mapping[ET.Element, ET.Element],
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
    parents: Mapping[ET.Element, ET.Element],
) -> str:
    current: ET.Element | None = element
    while current is not None:
        if key in current.attrib:
            return current.attrib[key]
        current = parents.get(current)
    return default


def _visible_item_element(
    element: ET.Element, parents: Mapping[ET.Element, ET.Element]
) -> bool:
    if element.tag == "t":
        if _has_ancestor(element, "n", parents):
            return False
        return _inherited(element, "Visible", "yes", parents) != "no"
    if element.tag == "embeddedobject":
        return True
    return not element.get("SupersededBy")


def _mapped_members(
    group: ET.Element,
    *,
    parents: Mapping[ET.Element, ET.Element],
    node_ids: Mapping[str, int],
    bindings: Mapping[str, list[str | None]],
    by_id: Mapping[str | None, ET.Element],
) -> dict[str, Any] | None:
    """Editor group record for ``group``, or None when it must stay XML-only."""
    if any(child is not group for child in group.iter("group")):
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
        if element is group or element.tag in _STRUCTURAL_TAGS:
            continue
        if element.tag == "n":
            if not _has_ancestor(element, "n", parents) and element not in claimed:
                return None
            continue
        if element.tag in _PROJECTED_ITEM_TAGS:
            if _visible_item_element(element, parents) and element not in claimed:
                return None
            continue
        return None

    if len(atoms) + len(items) < 2:
        return None
    return {"atoms": atoms, "items": items}


def native_group_records(
    page: ET.Element,
    *,
    parents: Mapping[ET.Element, ET.Element],
    node_ids: Mapping[str, int],
    bindings: Mapping[str, list[str | None]],
    by_id: Mapping[str | None, ET.Element],
) -> list[tuple[str, dict[str, Any]]]:
    """Native ID and disjoint editor group of each qualifying page-level group."""
    records: list[tuple[str, dict[str, Any]]] = []
    seen_atoms: set[int] = set()
    seen_items: set[tuple[str, int]] = set()
    for child in page:
        native_id = child.get("id")
        if child.tag != "group" or not native_id:
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
        item_refs = {(str(kind), int(index)) for kind, index in mapped["items"]}
        if seen_atoms.intersection(mapped["atoms"]) or seen_items & item_refs:
            continue
        seen_atoms.update(mapped["atoms"])
        seen_items.update(item_refs)
        records.append((native_id, mapped))
    return records


def editor_groups_from_native(
    page: ET.Element,
    *,
    parents: Mapping[ET.Element, ET.Element],
    node_ids: Mapping[str, int],
    bindings: Mapping[str, list[str | None]],
    by_id: Mapping[str | None, ET.Element],
) -> list[dict[str, Any]]:
    """Build disjoint editor groups for qualifying page-level native groups."""
    return [
        record
        for _, record in native_group_records(
            page,
            parents=parents,
            node_ids=node_ids,
            bindings=bindings,
            by_id=by_id,
        )
    ]


def _imported_native_groups(source: Mapping[str, Any]) -> dict[str, frozenset[str]]:
    """Native members of each group import mapped, from immutable provenance.

    The importer's mapping is recomputed from ``source["xml"]`` with baseline
    item bindings and its own top-level node order, never from the XML being
    written. A recomputed group counts only when the baseline holds the same
    editor group, so snapshots written before groups were mapped stay unmapped.
    """
    baseline_groups = source["baseline"].get("groups") or []
    if not baseline_groups:
        return {}
    root = parse_native_xml(source["xml"])
    page = root.find("page")
    if page is None:
        return {}
    parents = {child: parent for parent in root.iter() for child in parent}
    nodes = [e for e in page.iter("n") if not _has_ancestor(e, "n", parents)]
    node_native = [e.get("id") for e in nodes]
    by_id = {
        e.get("id"): e
        for e in root.iter()
        if e.get("id") and e.tag not in {"font", "objecttag"}
    }
    baseline_items = source["baseline_items"]
    bindings = {
        collection: list(baseline_items.get(collection, []))
        for collection in _ITEM_COLLECTIONS
    }
    imported: dict[str, frozenset[str]] = {}
    for native_id, record in native_group_records(
        page,
        parents=parents,
        node_ids={native: index for index, native in enumerate(node_native) if native},
        bindings=bindings,
        by_id=by_id,
    ):
        if record not in baseline_groups:
            continue
        members = {str(node_native[index]) for index in record["atoms"]}
        members.update(
            str(bindings[str(kind)][int(index)]) for kind, index in record["items"]
        )
        imported[native_id] = frozenset(members)
    return imported


def _native_ids(
    group: Mapping[str, Any],
    *,
    atom_native: Mapping[str, str],
    items: Mapping[str, list[str | None]],
) -> frozenset[str]:
    native_ids: set[str] = set()
    for atom_id in group.get("atoms", []):
        native = atom_native.get(str(atom_id))
        if native is not None:
            native_ids.add(native)
    for kind, index in group.get("items", []):
        bindings = items.get(str(kind), [])
        if isinstance(index, int) and 0 <= index < len(bindings):
            native = bindings[index]
            if native is not None:
                native_ids.add(native)
    return frozenset(native_ids)


def _refuse_unwrap(group: ET.Element, detail: str) -> None:
    raise ValueError(
        f"Ungrouping native group #{group.get('id')} would drop {detail}; "
        "group its members again before saving. The file was not replaced."
    )


def _unwrap_group(
    group: ET.Element,
    parents: dict[ET.Element, ET.Element],
    by_id: dict[str | None, ET.Element],
) -> None:
    unsupported = sorted(
        key
        for key in group.attrib
        if key not in _GROUP_OWN_KEYS and key not in INHERITED_STYLE_KEYS
    )
    if unsupported:
        _refuse_unwrap(group, f"its unsupported {', '.join(unsupported)} metadata")
    metadata = sorted({c.tag for c in group if c.tag in _GROUP_METADATA_TAGS})
    if metadata:
        _refuse_unwrap(group, f"its {', '.join(metadata)} metadata")
    parent = parents[group]
    children = list(group)
    for child in children:
        for key in INHERITED_STYLE_KEYS & group.attrib.keys():
            child.attrib.setdefault(key, group.attrib[key])
    index = list(parent).index(group)
    for offset, child in enumerate(children):
        group.remove(child)
        parent.insert(index + offset, child)
        parents[child] = parent
    if children:
        children[-1].tail = group.tail
    parent.remove(group)
    del parents[group]
    by_id.pop(group.get("id"), None)


def sync_native_groups_on_save(
    page: ET.Element,
    *,
    parents: dict[ET.Element, ET.Element],
    by_id: dict[str | None, ET.Element],
    state: Mapping[str, Any],
    source: Mapping[str, Any],
) -> set[str]:
    """Unwrap mapped native groups no editor group covers; return their IDs.

    Members deleted since import no longer count; a mapped group with fewer
    than two remaining members keeps its wrapper. Unwrapping refuses group
    attributes and metadata children it cannot carry to the group's children.
    """
    imported = _imported_native_groups(source)
    if not imported:
        return set()
    atom_native = {str(key): value for key, value in source["atoms"].items()}
    items: Mapping[str, list[str | None]] = source["items"]
    live: set[str] = {
        atom_native[str(key)]
        for key in state["model"]["atoms"]
        if str(key) in atom_native
    }
    for bindings in items.values():
        live.update(native for native in bindings if native is not None)
    editor_sets = [
        _native_ids(group, atom_native=atom_native, items=items)
        for group in state.get("groups") or []
    ]
    unwrapped: set[str] = set()
    for native_id, members in imported.items():
        remaining = members & live
        group = by_id.get(native_id)
        if (
            len(remaining) < 2
            or group is None
            or parents.get(group) is not page
            or any(remaining <= editor_set for editor_set in editor_sets)
        ):
            continue
        _unwrap_group(group, parents, by_id)
        unwrapped.add(native_id)
    return unwrapped
