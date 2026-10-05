"""Draw the first-scheme side chains with the tools the guides name.

The completed example has eight atoms and eight bonds on each side. One sprout
followed by an OH or O label replaces the new carbon and leaves seven of each.
This follows the drag counts written in the guides, through Ring and Bond tool
keys, pointer drags, and the atom and bond hotkeys. It does not inject atoms.
"""

from __future__ import annotations

import json
import math
import re
from collections import Counter
from pathlib import Path

from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtGui import QKeySequence
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QInputDialog

from tests.native_canvas_support import app as app
from tests.native_canvas_support import canvas as canvas

ROOT = Path(__file__).resolve().parents[1]
_GUIDES = (
    ROOT / "docs" / "FIRST_SCHEME.md",
    ROOT / "docs" / "FIRST_SCHEME.ko.md",
    ROOT / "README.md",
    ROOT / "README.ko.md",
)
_EXAMPLE = ROOT / "examples" / "first-scheme.chemvas"


def _collapse(text: str) -> str:
    return re.sub(r"\s+", " ", text)


def _structure_clauses(text: str) -> tuple[str, str]:
    """The alcohol instructions, then the product instructions, from one guide."""
    section = re.search(r"(?ms)^## 1\. [^\n]+\n(.*?)(?=^## |\Z)", text)
    if section is not None:
        body = section.group(1)
    else:
        bodies = re.findall(r"(?ms)^## [^\n]+\n(.*?)(?=^## |\Z)", text)
        body = next(
            item for item in bodies if "**Ring**" in item and "**Bond**" in item
        )
    alcohol, product = re.split(
        r"second benzene|오른쪽에도 벤젠", _collapse(body), maxsplit=1
    )
    product = re.split(r"\*\*Arrow\*\*|화살표", product, maxsplit=1)[0]
    return alcohol, product


def _drag_count(clause: str) -> int:
    return len(re.findall(r"\bdrag\b", clause, flags=re.IGNORECASE)) + clause.count(
        "끌어"
    )


def _double_target(clause: str) -> str | None:
    """Which substituent bond the guide tells the reader to restyle with `2`."""
    if "`2`" not in clause:
        return None
    if "second bond" in clause.lower() or "두 번째 결합" in clause:
        return "latest"
    return "first"


def _guide_recipe(text: str) -> tuple[int, int, str | None, bool]:
    alcohol, product = _structure_clauses(text)
    return (
        _drag_count(alcohol),
        _drag_count(product),
        _double_target(product),
        "OH" in alcohol,
    )


def _components(
    elements: dict[int, str], bonds: list[tuple[int, int, int]]
) -> list[tuple[dict[int, str], list[tuple[int, int, int]]]]:
    parent = {atom_id: atom_id for atom_id in elements}

    def find(atom_id: int) -> int:
        while parent[atom_id] != atom_id:
            parent[atom_id] = parent[parent[atom_id]]
            atom_id = parent[atom_id]
        return atom_id

    for left, right, _order in bonds:
        parent[find(left)] = find(right)
    groups: dict[int, set[int]] = {}
    for atom_id in elements:
        groups.setdefault(find(atom_id), set()).add(atom_id)
    found = []
    for atom_ids in groups.values():
        local = {atom_id: elements[atom_id] for atom_id in atom_ids}
        local_bonds = [
            bond for bond in bonds if bond[0] in atom_ids and bond[1] in atom_ids
        ]
        found.append((local, local_bonds))
    return found


def _signature(
    elements: dict[int, str], bonds: list[tuple[int, int, int]]
) -> tuple[int, int, str, str, int, int]:
    """Counts plus the terminal label and the two substituent bond orders."""
    degree: Counter[int] = Counter()
    for left, right, _order in bonds:
        degree[left] += 1
        degree[right] += 1
    terminals = [atom_id for atom_id in elements if degree[atom_id] == 1]
    assert len(terminals) == 1
    terminal = terminals[0]
    outer = next(bond for bond in bonds if terminal in bond[:2])
    neighbor = outer[1] if outer[0] == terminal else outer[0]
    inner = next(
        bond for bond in bonds if neighbor in bond[:2] and terminal not in bond[:2]
    )
    return (
        len(elements),
        len(bonds),
        elements[terminal],
        elements[neighbor],
        outer[2],
        inner[2],
    )


def _example_signatures() -> frozenset[tuple[int, int, str, str, int, int]]:
    document = json.loads(_EXAMPLE.read_text(encoding="utf-8"))
    model = document["state"]["model"]
    elements = {
        int(atom_id): atom["element"] for atom_id, atom in model["atoms"].items()
    }
    bonds = [(bond["a"], bond["b"], bond["order"]) for bond in model["bonds"]]
    return frozenset(
        _signature(group, group_bonds)
        for group, group_bonds in _components(elements, bonds)
    )


def _press_tool(canvas, app, keycap: str, tool_name: str) -> None:
    canvas.setFocus()
    combination = QKeySequence(keycap)[0]
    QTest.keyClick(canvas, combination.key(), combination.keyboardModifiers(), 0)
    app.processEvents()
    assert canvas.services.tool_controller.active.name == tool_name


def _click(canvas, app, scene_pos: QPointF) -> None:
    QTest.mouseClick(
        canvas.viewport(),
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
        canvas.mapFromScene(scene_pos),
        0,
    )
    app.processEvents()


def _key_at(canvas, app, monkeypatch, scene_pos: QPointF, key: Qt.Key) -> None:
    canvas.setFocus()
    global_pos = canvas.viewport().mapToGlobal(canvas.mapFromScene(scene_pos))
    with monkeypatch.context() as cursor:
        cursor.setattr("chemvas.ui.tools.hover.QCursor.pos", lambda: global_pos)
        QTest.keyClick(canvas, key, Qt.KeyboardModifier.NoModifier, 0)
    app.processEvents()


def _rightmost(canvas, atom_ids: set[int]) -> int:
    return max(
        atom_ids,
        key=lambda atom_id: (
            canvas.model.atoms[atom_id].x,
            -canvas.model.atoms[atom_id].y,
            atom_id,
        ),
    )


def _drag_from(canvas, app, atom_id: int) -> int:
    before = set(canvas.model.atoms)
    atom = canvas.model.atoms[atom_id]
    ids = _component_ids(canvas, atom_id)
    center_x = sum(canvas.model.atoms[item].x for item in ids) / len(ids)
    center_y = sum(canvas.model.atoms[item].y for item in ids) / len(ids)
    dx, dy = atom.x - center_x, atom.y - center_y
    norm = math.hypot(dx, dy) or 1.0
    length = canvas.renderer.style.bond_length_px * 2
    end = QPointF(atom.x + dx / norm * length, atom.y + dy / norm * length)
    viewport = canvas.viewport()
    QTest.mousePress(
        viewport,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
        canvas.mapFromScene(QPointF(atom.x, atom.y)),
        0,
    )
    app.processEvents()
    QTest.mouseMove(viewport, canvas.mapFromScene(end))
    app.processEvents()
    QTest.mouseRelease(
        viewport,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
        canvas.mapFromScene(end),
        0,
    )
    app.processEvents()
    added = set(canvas.model.atoms) - before
    assert len(added) == 1
    return next(iter(added))


def _component_ids(canvas, atom_id: int) -> set[int]:
    bonds = [(bond.a, bond.b) for bond in canvas.model.bonds if bond is not None]
    seen = {atom_id}
    pending = [atom_id]
    while pending:
        current = pending.pop()
        for left, right in bonds:
            other = right if left == current else left if right == current else None
            if other is not None and other not in seen:
                seen.add(other)
                pending.append(other)
    return seen


def _bond_between(canvas, left: int, right: int):
    wanted = {left, right}
    return next(
        bond
        for bond in canvas.model.bonds
        if bond is not None and {bond.a, bond.b} == wanted
    )


def _draw_side(
    canvas,
    app,
    monkeypatch,
    center: QPointF,
    *,
    drags: int,
    double_target: str | None,
    hydroxymethyl: bool,
) -> None:
    _press_tool(canvas, app, "J", "benzene")
    before = set(canvas.model.atoms)
    _click(canvas, app, center)
    ring = set(canvas.model.atoms) - before
    assert len(ring) == 6
    _press_tool(canvas, app, "X", "bond")
    origin = _rightmost(canvas, ring)
    created: list[int] = []
    current = origin
    for _ in range(drags):
        current = _drag_from(canvas, app, current)
        created.append(current)
    assert created
    if double_target == "first":
        ends = (origin, created[0])
    elif double_target == "latest":
        previous = origin if len(created) == 1 else created[-2]
        ends = (previous, created[-1])
    else:
        ends = None
    if ends is not None:
        bond = _bond_between(canvas, *ends)
        midpoint = _midpoint(canvas, *ends)
        _key_at(canvas, app, monkeypatch, midpoint, Qt.Key.Key_2)
        assert bond.order == 2
    terminal = canvas.model.atoms[created[-1]]
    _key_at(canvas, app, monkeypatch, QPointF(terminal.x, terminal.y), Qt.Key.Key_O)
    if hydroxymethyl:
        monkeypatch.setattr(
            QInputDialog, "getText", lambda *_args, **_kwargs: ("OH", True)
        )
        terminal = canvas.model.atoms[created[-1]]
        _key_at(
            canvas, app, monkeypatch, QPointF(terminal.x, terminal.y), Qt.Key.Key_Return
        )


def _midpoint(canvas, left: int, right: int) -> QPointF:
    start = canvas.model.atoms[left]
    end = canvas.model.atoms[right]
    return QPointF((start.x + end.x) / 2, (start.y + end.y) / 2)


def _drawn_signatures(canvas) -> frozenset[tuple[int, int, str, str, int, int]]:
    elements = {atom_id: atom.element for atom_id, atom in canvas.model.atoms.items()}
    bonds = [
        (bond.a, bond.b, bond.order) for bond in canvas.model.bonds if bond is not None
    ]
    return frozenset(
        _signature(group, group_bonds)
        for group, group_bonds in _components(elements, bonds)
    )


def test_first_scheme_guides_build_the_example_side_chains(canvas, app, monkeypatch):
    recipes = [_guide_recipe(path.read_text(encoding="utf-8")) for path in _GUIDES]
    assert len(set(recipes)) == 1, recipes
    alcohol_drags, product_drags, double_target, hydroxymethyl = recipes[0]
    canvas.centerOn(0, 0)
    app.processEvents()
    _draw_side(
        canvas,
        app,
        monkeypatch,
        QPointF(-160, 0),
        drags=alcohol_drags,
        double_target=None,
        hydroxymethyl=hydroxymethyl,
    )
    _draw_side(
        canvas,
        app,
        monkeypatch,
        QPointF(120, 0),
        drags=product_drags,
        double_target=double_target,
        hydroxymethyl=False,
    )
    assert _drawn_signatures(canvas) == _example_signatures()
