from __future__ import annotations

from collections.abc import Mapping, Sequence
from copy import deepcopy
from dataclasses import dataclass
from math import isfinite
from typing import Literal, cast

from chemvas.domain.document import (
    CANVAS_FILE_VERSION,
    build_document_payload,
    deserialize_model_state,
    is_document_number,
    is_hex_color,
)

MAX_LAYOUT_ROWS = 128
MAX_LAYOUT_BLOCKS = 128
MAX_LAYOUT_REFERENCES = 4096
_FORMAT = "chemvas-scheme-layout"
_ROOT_REQUIRED = frozenset(("format", "version", "source_sha256", "rows"))
_ROOT_ALLOWED = _ROOT_REQUIRED | {
    "gap",
    "row_gap",
    "caption_gap",
    "line_gap",
    "max_row_width",
    "mode",
    "caption_alignment",
    "arrow_color",
}
_ITEM_KINDS = frozenset(("notes", "ts_brackets", "shapes"))


@dataclass(frozen=True, slots=True)
class LayoutBlock:
    atoms: tuple[int, ...]
    captions: tuple[int, ...] = ()
    items: tuple[tuple[str, int], ...] = ()
    anchor_atom: int | None = None
    parts: tuple[tuple[int, ...], ...] = ()


@dataclass(frozen=True, slots=True)
class LayoutRow:
    blocks: tuple[LayoutBlock, ...]
    arrows: tuple[int, ...] = ()
    reference_blocks: tuple[int, ...] = ()
    column_group: str | None = None


@dataclass(frozen=True, slots=True)
class LayoutRequest:
    source_sha256: str
    rows: tuple[LayoutRow, ...]
    gap: float = 40.0
    row_gap: float = 30.0
    caption_gap: float = 10.0
    line_gap: float = 4.0
    max_row_width: float | None = None
    mode: Literal["arrange", "align-y"] = "arrange"
    caption_alignment: Literal["row", "structure"] = "row"
    arrow_color: str | None = None


def validate_layout_request(
    state: Mapping[str, object], request: object, *, source_sha256: str
) -> LayoutRequest:
    """Validate explicit rows without inferring or changing molecular structure."""
    root = _object(request, "layout", _ROOT_REQUIRED, _ROOT_ALLOWED)
    mode = _mode(root)
    if root["format"] != _FORMAT:
        raise ValueError(f"layout format must be {_FORMAT!r}")
    if type(root["version"]) is not int or root["version"] != 1:
        raise ValueError("layout version must be 1")
    digest = root["source_sha256"]
    if (
        not isinstance(digest, str)
        or len(digest) != 64
        or any(character not in "0123456789abcdef" for character in digest)
    ):
        raise ValueError("source_sha256 must be 64 lowercase hexadecimal characters")
    if digest != source_sha256:
        raise ValueError("source_sha256 does not match the exact input document bytes")
    if state.get("calculation_plan") is not None:
        raise ValueError(
            "explicit scheme layout supports 2D drawings without a Calculation Plan; "
            "adjust this document manually. No plan or source data was removed."
        )
    if state.get("perspective"):
        raise ValueError(
            "explicit scheme layout supports 2D drawings without perspective state; "
            "adjust this document manually. No perspective or source data was removed."
        )
    build_document_payload(dict(state), CANVAS_FILE_VERSION)
    model = deserialize_model_state(cast("Mapping[str, object]", state["model"]))
    rows: list[LayoutRow] = []
    atom_owners: dict[int, int] = {}
    item_owners: set[tuple[str, int]] = set()
    block_count = 0
    column_sizes: dict[str, int] = {}
    for row_index, raw_row in enumerate(
        _array(root["rows"], "rows", MAX_LAYOUT_ROWS, nonempty=True)
    ):
        name = f"row {row_index}"
        row = _object(
            raw_row,
            name,
            {"blocks"},
            {"blocks", "arrows", "reference_blocks", "column_group"},
        )
        blocks: list[LayoutBlock] = []
        for block_index, raw_block in enumerate(
            _array(row["blocks"], f"{name} blocks", MAX_LAYOUT_BLOCKS, nonempty=True)
        ):
            block_count += 1
            if block_count > MAX_LAYOUT_BLOCKS:
                raise ValueError(
                    f"layout may contain at most {MAX_LAYOUT_BLOCKS} blocks"
                )
            block = _block(raw_block, f"{name} block {block_index}", state, mode)
            for atom_id in block.atoms:
                if atom_id not in model.atoms:
                    raise ValueError(f"unknown atom reference {atom_id}")
                if atom_id in atom_owners:
                    raise ValueError(f"duplicate atom reference {atom_id}")
                atom_owners[atom_id] = block_count
                if len(atom_owners) > MAX_LAYOUT_REFERENCES:
                    raise ValueError(
                        f"layout may reference at most {MAX_LAYOUT_REFERENCES} atoms"
                    )
            for reference in _block_item_refs(block):
                _claim_item(reference, item_owners)
            blocks.append(block)
        arrows = _indices(row.get("arrows", []), f"{name} arrows")
        if "arrows" in row and len(arrows) != len(blocks) - 1:
            raise ValueError(
                f"{name} arrows must contain exactly blocks minus one entries"
            )
        for arrow_index in arrows:
            _check_arrow(state, arrow_index)
            _claim_item(("arrows", arrow_index), item_owners)
        references = _references(row, name, len(blocks), mode)
        column_group = _column_group(row, name, mode)
        if column_group is not None and column_sizes.setdefault(
            column_group, len(blocks)
        ) != len(blocks):
            raise ValueError(
                "rows in one column_group must have the same number of blocks"
            )
        rows.append(LayoutRow(tuple(blocks), arrows, references, column_group))
    part_owners = {
        atom: (row_index, block_index, part_index)
        for row_index, row in enumerate(rows)
        for block_index, block in enumerate(row.blocks)
        for part_index, part in enumerate(block.parts or (block.atoms,))
        for atom in part
    }
    for bond in model.bonds:
        if bond is not None and atom_owners.get(bond.a) != atom_owners.get(bond.b):
            raise ValueError(
                f"blocks must contain whole connected structures; bond {bond.a}–{bond.b} "
                "would cross a block boundary"
            )
        if bond is not None and part_owners.get(bond.a) != part_owners.get(bond.b):
            raise ValueError(
                f"parts must not cut bonds; bond {bond.a}–{bond.b} crosses a part boundary"
            )
    caption_alignment, arrow_color = _arrangement_style(root, rows)
    result = LayoutRequest(
        source_sha256=digest,
        rows=tuple(rows),
        gap=_distance(root.get("gap", 40), "gap", positive=True),
        row_gap=_distance(root.get("row_gap", 30), "row_gap"),
        caption_gap=_distance(root.get("caption_gap", 10), "caption_gap"),
        line_gap=_distance(root.get("line_gap", 4), "line_gap"),
        max_row_width=(
            _distance(
                root["max_row_width"], "max_row_width", maximum=100_000, positive=True
            )
            if "max_row_width" in root
            else None
        ),
        mode=mode,
        caption_alignment=caption_alignment,
        arrow_color=arrow_color,
    )
    merged_layout_groups(state, result)
    return result


def _mode(root: Mapping[str, object]) -> Literal["arrange", "align-y"]:
    mode = root.get("mode", "arrange")
    if mode not in ("arrange", "align-y"):
        raise ValueError("layout mode must be arrange or align-y")
    if mode == "align-y" and set(root) & {
        "gap",
        "row_gap",
        "caption_gap",
        "line_gap",
        "max_row_width",
        "caption_alignment",
        "arrow_color",
    }:
        raise ValueError(
            "align-y preserves positions outside Y alignment; omit gaps and max_row_width, "
            "caption_alignment and arrow_color"
        )
    return cast("Literal['arrange', 'align-y']", mode)


def _column_group(row: Mapping[str, object], name: str, mode: str) -> str | None:
    if "column_group" not in row:
        return None
    if mode == "align-y":
        raise ValueError("column_group is not used by align-y; omit it")
    value = row["column_group"]
    if (
        not isinstance(value, str)
        or not 1 <= len(value) <= 64
        or any(
            character.isspace() or not character.isprintable() for character in value
        )
    ):
        raise ValueError(
            f"{name} column_group must be 1–64 printable non-whitespace characters"
        )
    return value


def _arrangement_style(
    root: Mapping[str, object], rows: Sequence[LayoutRow]
) -> tuple[Literal["row", "structure"], str | None]:
    alignment = root.get("caption_alignment", "row")
    if alignment not in ("row", "structure"):
        raise ValueError("caption_alignment must be row or structure")
    color = None
    if "arrow_color" in root:
        if not is_hex_color(root["arrow_color"]):
            raise ValueError("arrow_color must be hexadecimal (#rgb or #rrggbb)")
        if not any(row.arrows for row in rows):
            raise ValueError("arrow_color requires at least one row arrow")
        color = cast("str", root["arrow_color"])
    return cast("Literal['row', 'structure']", alignment), color


def _references(
    row: Mapping[str, object], name: str, count: int, mode: str
) -> tuple[int, ...]:
    if "reference_blocks" not in row:
        return ()
    if mode != "align-y":
        raise ValueError("reference_blocks requires align-y mode")
    references = _indices(
        row["reference_blocks"], f"{name} reference_blocks", nonempty=True
    )
    if len(set(references)) != len(references) or any(i >= count for i in references):
        raise ValueError(
            f"{name} reference_blocks must be distinct existing block indices"
        )
    return references


def wrap_layout_row(
    block_widths: Sequence[float],
    arrow_widths: Sequence[float],
    *,
    gap: float,
    max_row_width: float,
) -> tuple[tuple[int, int], ...]:
    """Greedily split one logical row, retaining incoming arrows with targets.

    Return half-open block slices. A slice starting after block zero carries the
    preceding arrow at its left edge; arrows and blocks are never split, omitted
    or duplicated. Widths are native painted bounds including captions/labels.
    """
    gap = _distance(gap, "gap", positive=True)
    max_row_width = _distance(
        max_row_width, "max_row_width", maximum=100_000, positive=True
    )
    if not 1 <= len(block_widths) <= MAX_LAYOUT_BLOCKS:
        raise ValueError(f"row must contain 1 to {MAX_LAYOUT_BLOCKS} block widths")
    if len(arrow_widths) not in (0, len(block_widths) - 1):
        raise ValueError(
            "arrow widths must be empty or contain blocks minus one entries"
        )
    if any(
        not isfinite(width) or width <= 0 for width in (*block_widths, *arrow_widths)
    ):
        raise ValueError("painted block and arrow widths must be finite and positive")
    if block_widths[0] > max_row_width:
        raise ValueError(
            f"block 0 requires width {block_widths[0]:.6g}, exceeding max_row_width "
            f"{max_row_width:.6g}; increase the width or edit the source layout"
        )
    # Check every indivisible unit before returning any layout plan.
    for index in range(1, len(block_widths)):
        incoming = arrow_widths[index - 1] + gap if arrow_widths else 0.0
        required = incoming + block_widths[index]
        if required > max_row_width:
            subject = (
                f"incoming arrow {index - 1} and block {index}"
                if arrow_widths
                else f"block {index}"
            )
            raise ValueError(
                f"{subject} require width {required:.6g}, exceeding max_row_width "
                f"{max_row_width:.6g}; increase the width or edit the source layout"
            )
    slices: list[tuple[int, int]] = []
    start = 0
    width = block_widths[0]
    for index in range(1, len(block_widths)):
        incoming = arrow_widths[index - 1] + gap if arrow_widths else 0.0
        required = incoming + block_widths[index]
        if width + gap + required <= max_row_width:
            width += gap + required
        else:
            slices.append((start, index))
            start, width = index, required
    slices.append((start, len(block_widths)))
    return tuple(slices)


def merged_layout_groups(
    state: Mapping[str, object], request: LayoutRequest
) -> list[dict[str, object]]:
    """Return native groups for a validated request, preserving untouched groups.

    Blocks replace only wholly contained groups. Row arrows remain separate and
    may retain an existing sole-member group. The source state is never mutated.
    """
    blocks = [block for row in request.rows for block in row.blocks]
    block_members = [_block_members(block) for block in blocks]
    moved_arrows = {("arrows", index) for row in request.rows for index in row.arrows}
    groups: list[dict[str, object]] = []
    for raw_group in cast("list[dict[str, object]]", state.get("groups", [])):
        members = {
            ("atoms", atom_id) for atom_id in cast("list[int]", raw_group["atoms"])
        } | {
            (kind, index)
            for kind, index in cast("list[tuple[str, int]]", raw_group["items"])
        }
        overlapping = [target for target in block_members if members & target]
        if overlapping:
            if len(overlapping) != 1 or not members <= overlapping[0]:
                raise ValueError(
                    "layout would split an existing group; include every group member "
                    "in one block or leave the group untouched"
                )
            continue
        if members & moved_arrows and len(members) != 1:
            raise ValueError(
                "a row arrow belongs to a mixed group; leave that group untouched "
                "or ungroup it explicitly in the GUI first"
            )
        groups.append(deepcopy(raw_group))
    groups.extend(
        {
            "atoms": list(block.atoms),
            "items": [list(reference) for reference in _block_item_refs(block)],
        }
        for block in blocks
    )
    if request.mode == "align-y":
        return deepcopy(cast("list[dict[str, object]]", state.get("groups", [])))
    return groups


def _block(
    value: object, name: str, state: Mapping[str, object], mode: str
) -> LayoutBlock:
    raw = _object(
        value, name, {"atoms"}, {"atoms", "captions", "items", "anchor_atom", "parts"}
    )
    atoms = _indices(raw["atoms"], f"{name} atoms", nonempty=True)
    captions = _indices(raw.get("captions", []), f"{name} captions")
    for index in captions:
        _check_item(state, "notes", index)
    items: list[tuple[str, int]] = []
    for item in _array(raw.get("items", []), f"{name} items", MAX_LAYOUT_REFERENCES):
        if not isinstance(item, list) or len(item) != 2:
            raise ValueError(f"{name} items must contain [kind, index] references")
        kind, index = item
        if not isinstance(kind, str) or kind not in _ITEM_KINDS:
            raise ValueError(f"{name} item kind must be notes, ts_brackets, or shapes")
        if type(index) is not int or index < 0:
            raise ValueError(f"{name} item index must be a non-negative integer")
        _check_item(state, kind, index)
        items.append((kind, index))
    anchor = raw.get("anchor_atom")
    if "anchor_atom" in raw and (type(anchor) is not int or anchor not in atoms):
        raise ValueError(f"{name} anchor_atom must be an atom in that block")
    if mode == "align-y" and "anchor_atom" in raw:
        raise ValueError("align-y measures molecular bounds; omit anchor_atom")
    parts = _parts(raw, name, atoms, mode)
    if len(parts) > 1 and any(kind != "notes" for kind, _ in items):
        raise ValueError(
            "multi-part blocks cannot move brackets or shapes; use one rigid part"
        )
    return LayoutBlock(atoms, captions, tuple(items), cast("int | None", anchor), parts)


def _parts(
    raw: Mapping[str, object], name: str, atoms: tuple[int, ...], mode: str
) -> tuple[tuple[int, ...], ...]:
    if "parts" not in raw:
        return ()
    if mode != "align-y":
        raise ValueError("parts requires align-y mode")
    parts: list[tuple[int, ...]] = []
    seen: set[int] = set()
    for part in _array(raw["parts"], f"{name} parts", len(atoms), nonempty=True):
        ids = _indices(part, f"{name} part atoms", nonempty=True)
        if len(ids) != len(set(ids)) or seen.intersection(ids):
            raise ValueError(f"{name} parts contain duplicate atom references")
        if not set(ids).issubset(atoms):
            raise ValueError(f"{name} part atoms must belong to that block")
        seen.update(ids)
        parts.append(ids)
    if seen != set(atoms):
        raise ValueError(f"{name} parts must include every block atom exactly once")
    return tuple(parts)


def _block_item_refs(block: LayoutBlock) -> tuple[tuple[str, int], ...]:
    return block.items + tuple(("notes", index) for index in block.captions)


def _block_members(block: LayoutBlock) -> set[tuple[str, int]]:
    return {("atoms", atom_id) for atom_id in block.atoms} | set(
        _block_item_refs(block)
    )


def _claim_item(reference: tuple[str, int], claimed: set[tuple[str, int]]) -> None:
    if reference in claimed:
        raise ValueError(
            f"duplicate scene item reference {reference[0]} {reference[1]}"
        )
    claimed.add(reference)
    if len(claimed) > MAX_LAYOUT_REFERENCES:
        raise ValueError(
            f"layout may reference at most {MAX_LAYOUT_REFERENCES} scene items"
        )


def _check_item(state: Mapping[str, object], kind: str, index: int) -> None:
    if index >= len(cast("list[object]", state[kind])):
        raise ValueError(f"unknown scene item reference {kind} {index}")


def _check_arrow(state: Mapping[str, object], index: int) -> None:
    _check_item(state, "arrows", index)
    arrow = cast("list[Mapping[str, object]]", state["arrows"])[index]
    start = cast("Sequence[float]", arrow["start"])
    end = cast("Sequence[float]", arrow["end"])
    if (
        arrow["kind"] not in {"arrow", "equilibrium"}
        or end[0] <= start[0]
        or abs(end[1] - start[1]) > 1e-6
    ):
        raise ValueError(
            f"row arrow {index} requires a left-to-right horizontal arrow or "
            "equilibrium arrow; adjust it in the GUI or omit it from the layout"
        )


def _indices(value: object, name: str, *, nonempty: bool = False) -> tuple[int, ...]:
    values = _array(value, name, MAX_LAYOUT_REFERENCES, nonempty=nonempty)
    if any(type(item) is not int or item < 0 for item in values):
        raise ValueError(f"{name} must contain non-negative integer indices")
    return tuple(cast("list[int]", values))


def _array(
    value: object, name: str, maximum: int, *, nonempty: bool = False
) -> list[object]:
    if not isinstance(value, list) or (nonempty and not value):
        qualifier = "a non-empty" if nonempty else "a"
        raise ValueError(f"{name} must be {qualifier} JSON array")
    if len(value) > maximum:
        raise ValueError(f"{name} may contain at most {maximum} entries")
    return value


def _object(
    value: object,
    name: str,
    required: frozenset[str] | set[str],
    allowed: frozenset[str] | set[str],
) -> Mapping[str, object]:
    if not isinstance(value, Mapping) or not required <= set(value) <= allowed:
        raise ValueError(f"{name} has missing or unknown keys")
    return value


def _distance(
    value: object, name: str, *, maximum: int = 10_000, positive: bool = False
) -> float:
    if (
        not is_document_number(value)
        or not 0 <= cast("float", value) <= maximum
        or (positive and value == 0)
    ):
        lower = "greater than 0" if positive else "at least 0"
        raise ValueError(f"{name} must be finite, {lower}, and at most {maximum}")
    return float(cast("float", value))
