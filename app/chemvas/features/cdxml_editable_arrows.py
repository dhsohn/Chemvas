"""Map representable native strokes to editable annotations without losing IDs."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import xml.etree.ElementTree as ET


def editable_arrow(reader: Any, e: ET.Element) -> dict[str, Any] | None:
    if e.tag == "arrow":
        if reader.number(e.get("AngularSize", "0"), e):
            return None
        start = reader.point(e.get("Tail3D", ""), e, 3)
        end = reader.point(e.get("Head3D", ""), e, 3)
        head, tail = e.get("ArrowheadHead", "None"), e.get("ArrowheadTail", "None")
    elif e.tag == "graphic" and e.get("GraphicType") == "Line":
        values = e.get("BoundingBox", "").split()
        if len(values) != 4:
            reader.unsupported(e, "line endpoints")
        end = reader.point(" ".join(values[:2]), e)
        start = reader.point(" ".join(values[2:]), e)
        head = {"NoHead": "None", "FullHead": "Full"}.get(
            e.get("ArrowType", "NoHead"), "Unsupported"
        )
        tail = "None"
    else:
        return None
    line = e.get("LineType", "Solid")
    if line not in {"Solid", "Dashed", "Bold", "Dashed Bold", "Bold Dashed"}:
        return None
    mirrored = False
    if head == tail == "None":
        kind = (
            "line_dashed"
            if "Dashed" in line
            else "line_bold"
            if "Bold" in line
            else "line"
        )
    elif (head, tail) in {("Full", "None"), ("None", "Full")}:
        if tail == "Full":
            start, end = end, start
        kind = "dotted" if "Dashed" in line else "arrow"
    elif head == tail and head in {"HalfLeft", "HalfRight"}:
        kind = "equilibrium"
        mirrored = head == "HalfRight"
    else:
        return None
    width = reader.number(reader.inherited(e, "LineWidth", "0.6"), e)
    if not 0 < width <= 100:
        reader.unsupported(e, "line width")
    for name, default in (
        ("HeadSize", "600"),
        ("ArrowheadWidth", "200"),
        ("ArrowShaftSpacing", "300"),
    ):
        reader.number(e.get(name, default), e)
    record = dict(kind=kind, start=start, end=end, color=reader.color(e))
    if mirrored:
        record["mirrored"] = True
    return record


def update_arrow(
    e: ET.Element,
    before: dict[str, Any],
    after: dict[str, Any],
    offset: list[float],
    color_index: Any,
) -> None:
    """Change owned coordinates/style only; unrelated native attributes survive."""
    if any(after.get("labels", {}).values()):
        raise ValueError("Native arrow labels require separate text objects.")
    kind = after["kind"]
    if kind not in {
        "line",
        "line_dashed",
        "line_bold",
        "arrow",
        "dotted",
        "equilibrium",
    }:
        raise ValueError(
            f"Native arrow type {kind} is not representable by this stroke."
        )
    start, end = after["start"], after["end"]

    def point(p: list[float] | tuple[float, ...], three: bool = True) -> str:
        value = f"{p[0] + offset[0]:.12g} {p[1] + offset[1]:.12g}"
        return value + " 0" if three else value

    same_style = kind == before["kind"] and after.get("mirrored", False) == before.get(
        "mirrored", False
    )
    if e.tag == "graphic" and same_style:
        e.set("BoundingBox", point(end, False) + " " + point(start, False))
    else:
        if e.tag == "graphic":
            e.tag = "arrow"
            for key in ("GraphicType", "ArrowType", "BoundingBox"):
                e.attrib.pop(key, None)
        if (
            same_style
            and e.get("ArrowheadTail") == "Full"
            and e.get("ArrowheadHead", "None") == "None"
        ):
            start, end = end, start
        e.set("Tail3D", point(start))
        e.set("Head3D", point(end))
        # BoundingBox is a cache and must not retain the pre-edit geometry.
        e.attrib.pop("BoundingBox", None)
        if not same_style:
            half = "HalfRight" if after.get("mirrored") else "HalfLeft"
            e.set(
                "ArrowheadHead",
                half
                if kind == "equilibrium"
                else "Full"
                if kind in {"arrow", "dotted"}
                else "None",
            )
            e.set("ArrowheadTail", half if kind == "equilibrium" else "None")
        if kind != before["kind"]:
            e.set(
                "LineType",
                "Dashed"
                if kind in {"line_dashed", "dotted"}
                else "Bold"
                if kind == "line_bold"
                else "Solid",
            )
    if after.get("color") != before.get("color"):
        e.set("color", color_index(after.get("color") or "#000000"))


def promote_snapshot_arrows(state: dict[str, Any]) -> None:
    """Upgrade old native image bindings, preserving edits and group membership."""
    from copy import deepcopy

    from chemvas.features.cdxml_preservation import PreservingImporter

    source = state.get("cdxml_source")
    if source is None or not source["items"].get("images"):
        return
    reader = PreservingImporter(source["xml"])
    byid = {e.get("id"): e for e in reader.root.iter()}
    baseline = source["baseline"]
    old_images = dict(
        zip(
            source["baseline_items"].get("images", []),
            baseline.get("images", []),
            strict=True,
        )
    )
    promoted = {}
    for identity, image in zip(
        source["items"]["images"], state.get("images", []), strict=True
    ):
        if identity is None or identity not in old_images:
            continue
        before = old_images[identity]
        if image["data_base64"] != before["data_base64"] or image.get(
            "opacity", 1
        ) != before.get("opacity", 1):
            continue
        arrow = editable_arrow(reader, byid[identity])
        if arrow is not None:
            promoted[identity] = arrow
    if not promoted:
        return
    for projection, bindings, live in (
        (state, source["items"], True),
        (baseline, source["baseline_items"], False),
    ):
        arrows = projection.setdefault("arrows", [])
        arrow_ids = bindings.setdefault("arrows", [None] * len(arrows))
        images: list[dict[str, Any]] = []
        image_ids: list[str | None] = []
        remap: dict[int, list[Any]] = {}
        for index, (identity, image) in enumerate(
            zip(bindings.get("images", []), projection.get("images", []), strict=True)
        ):
            if identity in promoted:
                arrow = deepcopy(promoted[identity])
                if live:
                    before = old_images[identity]
                    for key in ("start", "end"):
                        arrow[key] = [
                            image[axis]
                            + (arrow[key][i] - before[axis])
                            * image[size]
                            / before[size]
                            for i, (axis, size) in enumerate(
                                (("x", "width"), ("y", "height"))
                            )
                        ]
                remap[index] = ["arrows", len(arrows)]
                arrows.append(arrow)
                arrow_ids.append(identity)
            else:
                remap[index] = ["images", len(images)]
                images.append(image)
                image_ids.append(identity)
        projection["images"] = images
        bindings["images"] = image_ids
        for group in projection.get("groups", []):
            group["items"] = [
                remap[index] if kind == "images" else [kind, index]
                for kind, index in group["items"]
            ]
