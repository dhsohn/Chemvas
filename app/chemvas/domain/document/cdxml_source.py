"""Validated native CDXML provenance retained by document saves and recovery.

This is document content, not a pointer to a mutable file on disk. Bindings use
source object IDs; collection bindings are parallel to the saved item arrays.

Coupled collection and native-link mutations for notes and image-to-arrow
promotion are owned here so callers cannot update one side alone.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from copy import deepcopy
from typing import TYPE_CHECKING, Any, TypedDict, cast
from xml.parsers import expat

if TYPE_CHECKING:
    from collections.abc import Mapping, MutableMapping, Sequence

from .state_values import _is_number

MAX_CDXML_SOURCE_BYTES = 16 * 1024 * 1024
COLLECTIONS = frozenset(
    ("notes", "arrows", "shapes", "images", "marks", "orbitals", "ts_brackets")
)


class CdxmlSource(TypedDict):
    """Saved native provenance fields retained beside document state."""

    xml: str
    offset: list[float]
    atoms: dict[str, str]
    bonds: dict[str, str]
    items: dict[str, list[str | None]]
    baseline: dict[str, Any]
    baseline_items: dict[str, list[str | None]]


class ImageArrowPromotion(TypedDict):
    """Distinct live and baseline arrow records for one native image identity."""

    live: dict[str, Any]
    baseline: dict[str, Any]


class UnsafeCdxmlDeclarationsError(ValueError):
    """Entity declarations or an internal DOCTYPE subset are present."""


def reject_unsafe_cdxml_declarations(text: str) -> None:
    """Reject entity declarations and any internal DOCTYPE subset.

    External DOCTYPE declarations without an internal subset remain allowed.
    Malformed input is passed through on purpose; callers must parse the same
    string with ElementTree immediately after this guard. Callers map this
    error to their own user-facing message.
    """
    if "<!ENTITY" in text:
        raise UnsafeCdxmlDeclarationsError(
            "CDXML entity declarations are not supported."
        )

    class _InternalSubsetError(Exception):
        pass

    class _StopAtRootError(Exception):
        pass

    parser = expat.ParserCreate()
    parser.SetParamEntityParsing(expat.XML_PARAM_ENTITY_PARSING_NEVER)

    def start_doctype(
        _name: str,
        _sysid: str | None,
        _pubid: str | None,
        has_internal_subset: int,
    ) -> None:
        if has_internal_subset:
            raise _InternalSubsetError

    def start_element(_name: str, _attrs: dict[str, str]) -> None:
        raise _StopAtRootError

    parser.StartDoctypeDeclHandler = start_doctype
    parser.StartElementHandler = start_element
    try:
        parser.Parse(text, True)
    except _InternalSubsetError as exc:
        raise UnsafeCdxmlDeclarationsError(
            "CDXML internal DOCTYPE subsets are not supported."
        ) from exc
    except _StopAtRootError:
        return
    except expat.ExpatError:
        # Malformed input is reported by the caller's ElementTree parse.
        return


def parse_native_xml(xml: str) -> ET.Element:
    if not isinstance(xml, str) or len(xml.encode("utf-8")) > MAX_CDXML_SOURCE_BYTES:
        raise ValueError("Invalid or oversized native CDXML source.")
    try:
        reject_unsafe_cdxml_declarations(xml)
    except UnsafeCdxmlDeclarationsError as exc:
        raise ValueError(
            "CDXML entity declarations and internal DTDs are not supported."
        ) from exc
    try:
        root = ET.fromstring(xml)
    except ET.ParseError as exc:
        raise ValueError("Invalid native CDXML source.") from exc
    if root.tag != "CDXML" or len(root.findall("page")) != 1:
        raise ValueError("Native CDXML editing requires one page.")
    objects = list(root.iter())
    if len(objects) > 100_000:
        raise ValueError("Too many native CDXML objects.")
    return root


def validate_cdxml_source(source: object, state: Mapping[str, object]) -> ET.Element:
    """Validate retained provenance and return its freshly parsed native tree.

    Bindings are checked against what the native writer relies on, not only
    that their IDs exist: atom and bond keys name baseline records, an atom
    binds a top-level ``<n>``, and a bond binds a ``<b>`` joining its atoms'
    bound nodes.
    """
    if not isinstance(source, dict) or set(source) != {
        "xml",
        "offset",
        "atoms",
        "bonds",
        "items",
        "baseline",
        "baseline_items",
    }:
        raise ValueError("Invalid CDXML source fields.")
    root = parse_native_xml(source["xml"])
    object_ids = [
        e.attrib["id"]
        for e in root.iter()
        if e.tag not in {"font", "objecttag"} and e.get("id") is not None
    ]
    ids = set(object_ids)
    if len(ids) != len(object_ids):
        raise ValueError("Duplicate native CDXML object IDs.")
    offset = source["offset"]
    if (
        not isinstance(offset, (list, tuple))
        or len(offset) != 2
        or any(not _is_number(v) for v in offset)
    ):
        raise ValueError("Invalid CDXML coordinate offset.")
    for key in ("atoms", "bonds"):
        values = source[key]
        if not isinstance(values, dict) or any(
            not all(part.isdigit() for part in str(k).split(":"))
            or not isinstance(v, str)
            or v not in ids
            for k, v in values.items()
        ):
            raise ValueError(f"Invalid CDXML {key} bindings.")
        if len(set(values.values())) != len(values):
            raise ValueError(f"Duplicate CDXML {key} binding.")
    _validate_item_bindings(source["items"], state, ids)
    baseline = source["baseline"]
    if not isinstance(baseline, dict) or "cdxml_source" in baseline:
        raise ValueError("Invalid recursive CDXML baseline.")
    from .state_validation import _validate_canvas_state

    _validate_canvas_state(baseline)
    _validate_item_bindings(source["baseline_items"], baseline, ids)
    _validate_structure_bindings(source, baseline, root)
    return root


def _validate_structure_bindings(
    source: Mapping[str, Any], baseline: Mapping[str, Any], root: ET.Element
) -> None:
    """Tie atom and bond bindings to baseline records and their native roles.

    Bindings are keyed by the baseline model, which survives later deletions
    in the live model, so deleted atoms and bonds stay valid here.
    """
    by_id = {
        e.attrib["id"]: e
        for e in root.iter()
        if e.tag not in {"font", "objecttag"} and e.get("id") is not None
    }
    inside_atom = {
        descendant
        for node in root.iter("n")
        for child in node
        for descendant in child.iter()
    }
    model = baseline["model"]
    baseline_atoms = {str(atom_id) for atom_id in model["atoms"]}
    atoms: Mapping[str, str] = source["atoms"]
    for key, native_id in atoms.items():
        node = by_id[native_id]
        if str(key) not in baseline_atoms or node.tag != "n" or node in inside_atom:
            raise ValueError("Invalid CDXML atoms bindings.")
    native_atoms = {str(key): native_id for key, native_id in atoms.items()}
    baseline_bonds = {
        f"{min(bond['a'], bond['b'])}:{max(bond['a'], bond['b'])}"
        for bond in model["bonds"]
        if bond is not None
    }
    bonds: Mapping[str, str] = source["bonds"]
    for key, native_id in bonds.items():
        ends = str(key).split(":")
        node = by_id[native_id]
        if (
            len(ends) != 2
            or str(key) not in baseline_bonds
            or node.tag != "b"
            or node in inside_atom
            or any(end not in native_atoms for end in ends)
            or {node.get("B"), node.get("E")} != {native_atoms[end] for end in ends}
        ):
            raise ValueError("Invalid CDXML bonds bindings.")


def native_ids_for_collection(
    items: Mapping[str, object], kind: str, count: int
) -> list[str | None]:
    """Return parallel native IDs. A missing collection means every item is unbound."""
    if kind not in COLLECTIONS:
        raise ValueError(f"Invalid CDXML {kind} bindings.")
    if kind not in items:
        return [None] * count
    bindings = items[kind]
    if not isinstance(bindings, list) or len(bindings) != count:
        raise ValueError(f"Invalid CDXML {kind} bindings.")
    if any(v is not None and not isinstance(v, str) for v in bindings):
        raise ValueError(f"Invalid CDXML {kind} bindings.")
    present = [v for v in bindings if v is not None]
    if len(set(present)) != len(present):
        raise ValueError(f"Duplicate CDXML {kind} binding.")
    return cast("list[str | None]", list(bindings))


def append_unbound_note(
    state: MutableMapping[str, Any], note: Mapping[str, object]
) -> int:
    """Append one note and its unbound native link; leave baseline untouched."""
    notes_obj = state.get("notes", [])
    if not isinstance(notes_obj, list):
        raise ValueError("Invalid notes collection.")
    notes = cast("list[Any]", notes_obj)
    index = len(notes)
    source = state.get("cdxml_source")
    if source is None:
        notes.append(note)
        return index
    if not isinstance(source, dict) or "items" not in source:
        raise ValueError("Invalid CDXML source fields.")
    items = source["items"]
    if not isinstance(items, dict) or not set(items) <= COLLECTIONS:
        raise ValueError("Invalid CDXML item bindings.")
    if "notes" in items:
        staged_links = native_ids_for_collection(items, "notes", index)
        staged_links.append(None)
    else:
        # Omitted notes bindings mean every existing note is unbound; appending
        # materializes the parallel unbound list, matching prior caller behavior.
        staged_links = [None] * (index + 1)
    notes.append(note)
    items["notes"] = staged_links
    return index


def promote_linked_images_to_arrows(
    state: MutableMapping[str, Any],
    promotions: Mapping[str, ImageArrowPromotion],
) -> None:
    """Move linked images to arrows in live and baseline together, or change nothing."""
    if not promotions:
        return
    if any(not isinstance(native_id, str) or not native_id for native_id in promotions):
        raise ValueError("Invalid CDXML images promotion identity.")
    for promotion in promotions.values():
        if (
            not isinstance(promotion, dict)
            or set(promotion) != {"live", "baseline"}
            or not isinstance(promotion["live"], dict)
            or not isinstance(promotion["baseline"], dict)
        ):
            raise ValueError("Invalid CDXML image-to-arrow promotion records.")

    source = state.get("cdxml_source")
    if (
        not isinstance(source, dict)
        or "items" not in source
        or "baseline" not in source
    ):
        raise ValueError("Invalid CDXML source fields.")
    live_items = source["items"]
    baseline_items = source["baseline_items"]
    baseline = source["baseline"]
    if (
        not isinstance(live_items, dict)
        or not isinstance(baseline_items, dict)
        or not isinstance(baseline, dict)
        or not set(live_items) <= COLLECTIONS
        or not set(baseline_items) <= COLLECTIONS
    ):
        raise ValueError("Invalid CDXML item bindings.")

    staged_live = _stage_image_arrow_promotion(state, live_items, promotions, live=True)
    staged_baseline = _stage_image_arrow_promotion(
        baseline, baseline_items, promotions, live=False
    )

    state["images"] = staged_live.images
    state["arrows"] = staged_live.arrows
    if staged_live.groups is not None:
        state["groups"] = staged_live.groups
    live_items["images"] = staged_live.image_ids
    live_items["arrows"] = staged_live.arrow_ids

    baseline["images"] = staged_baseline.images
    baseline["arrows"] = staged_baseline.arrows
    if staged_baseline.groups is not None:
        baseline["groups"] = staged_baseline.groups
    baseline_items["images"] = staged_baseline.image_ids
    baseline_items["arrows"] = staged_baseline.arrow_ids


class _StagedPromotion:
    __slots__ = ("images", "image_ids", "arrows", "arrow_ids", "groups")

    def __init__(
        self,
        images: list[Any],
        image_ids: list[str | None],
        arrows: list[Any],
        arrow_ids: list[str | None],
        groups: list[dict[str, Any]] | None,
    ) -> None:
        self.images = images
        self.image_ids = image_ids
        self.arrows = arrows
        self.arrow_ids = arrow_ids
        self.groups = groups


def _stage_image_arrow_promotion(
    projection: Mapping[str, Any],
    bindings: Mapping[str, object],
    promotions: Mapping[str, ImageArrowPromotion],
    *,
    live: bool,
) -> _StagedPromotion:
    images_obj = projection.get("images", [])
    arrows_obj = projection.get("arrows", [])
    if not isinstance(images_obj, list) or not isinstance(arrows_obj, list):
        raise ValueError("Invalid CDXML image or arrow collection.")
    images = cast("list[Any]", images_obj)
    arrows = cast("list[Any]", arrows_obj)

    if "images" not in bindings:
        raise ValueError("Invalid CDXML images bindings.")
    image_ids = native_ids_for_collection(bindings, "images", len(images))
    arrow_ids = native_ids_for_collection(bindings, "arrows", len(arrows))

    present_image_ids = {identity for identity in image_ids if identity is not None}
    for native_id in promotions:
        if native_id not in present_image_ids:
            raise ValueError(f"Missing CDXML images binding for {native_id}.")
    # Duplicate image bindings are already rejected by native_ids_for_collection.

    retained_images: list[Any] = []
    retained_image_ids: list[str | None] = []
    staged_arrows = list(arrows)
    staged_arrow_ids = list(arrow_ids)
    remap: dict[int, list[Any]] = {}
    for index, (identity, image) in enumerate(zip(image_ids, images, strict=True)):
        if identity is not None and identity in promotions:
            promotion = promotions[identity]
            arrow = deepcopy(promotion["live"] if live else promotion["baseline"])
            remap[index] = ["arrows", len(staged_arrows)]
            staged_arrows.append(arrow)
            staged_arrow_ids.append(identity)
        else:
            remap[index] = ["images", len(retained_images)]
            retained_images.append(image)
            retained_image_ids.append(identity)

    present_arrows = [value for value in staged_arrow_ids if value is not None]
    if len(set(present_arrows)) != len(present_arrows):
        raise ValueError("Duplicate CDXML arrows binding.")

    groups_obj = projection.get("groups")
    staged_groups: list[dict[str, Any]] | None
    if groups_obj is None:
        staged_groups = None
    else:
        if not isinstance(groups_obj, list):
            raise ValueError("Invalid group references.")
        collection_counts = {
            key: (
                len(cast("list[Any]", projection[key]))
                if isinstance(projection.get(key), list)
                else 0
            )
            for key in COLLECTIONS
        }
        staged_groups = []
        for group in groups_obj:
            if not isinstance(group, dict) or "items" not in group:
                raise ValueError("Invalid group references.")
            items = group["items"]
            if not isinstance(items, list):
                raise ValueError("Invalid group references.")
            remapped: list[list[Any]] = []
            for reference in items:
                if (
                    not isinstance(reference, (list, tuple))
                    or len(reference) != 2
                    or not isinstance(reference[0], str)
                    or not isinstance(reference[1], int)
                ):
                    raise ValueError("Invalid group references.")
                kind, index = reference[0], reference[1]
                if kind == "images":
                    if not 0 <= index < len(images):
                        raise ValueError("Invalid group image reference.")
                    remapped.append(list(remap[index]))
                    continue
                if kind in COLLECTIONS and not 0 <= index < collection_counts[kind]:
                    raise ValueError(f"Invalid group {kind} reference.")
                remapped.append([kind, index])
            staged_groups.append({**group, "items": remapped})
        _validate_staged_group_indexes(
            staged_groups,
            {
                **collection_counts,
                "images": len(retained_images),
                "arrows": len(staged_arrows),
            },
        )

    return _StagedPromotion(
        retained_images,
        retained_image_ids,
        staged_arrows,
        staged_arrow_ids,
        staged_groups,
    )


def _validate_staged_group_indexes(
    groups: Sequence[Mapping[str, Any]], counts: Mapping[str, int]
) -> None:
    seen: set[tuple[str, int]] = set()
    for group in groups:
        items = group["items"]
        if not isinstance(items, list):
            raise ValueError("Invalid group references.")
        for reference in items:
            kind, index = reference[0], reference[1]
            if kind not in counts:
                continue
            key = (kind, index)
            if not 0 <= index < counts[kind] or key in seen:
                raise ValueError(f"Invalid group {kind} reference.")
            seen.add(key)


def _validate_item_bindings(
    items: object, state: Mapping[str, object], ids: set[str]
) -> None:
    if not isinstance(items, dict) or not set(items) <= COLLECTIONS:
        raise ValueError("Invalid CDXML item bindings.")
    for key, bindings in items.items():
        values = state.get(key, [])
        if (
            not isinstance(values, list)
            or not isinstance(bindings, list)
            or len(bindings) != len(values)
            or any(
                v is not None and (not isinstance(v, str) or v not in ids)
                for v in bindings
            )
        ):
            raise ValueError(f"Invalid CDXML {key} bindings.")
        present = [v for v in bindings if v is not None]
        if len(set(present)) != len(present):
            raise ValueError(f"Duplicate CDXML {key} binding.")
