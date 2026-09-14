"""Shared canvas doubles and scene builders for operation tests."""

import os
from types import SimpleNamespace

from tests.runtime_services import canvas_runtime_services
from tests.runtime_state import canvas_runtime_state

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QPointF, QRectF
from PyQt6.QtGui import QBrush, QColor, QImage, QPolygonF
from PyQt6.QtWidgets import (
    QGraphicsItem,
    QGraphicsPolygonItem,
    QGraphicsRectItem,
    QGraphicsScene,
    QGraphicsTextItem,
)

from chemvas.domain.document import Atom, Bond, MoleculeModel
from chemvas.ui.atom_coords_access import (
    CanvasAtomCoords3DState,
    atom_coords_3d_for,
)
from chemvas.ui.canvas_atom_graphics_state import (
    CanvasAtomGraphicsState,
    atom_dots_for,
    atom_items_for,
    set_atom_dots_for,
    set_atom_items_for,
)
from chemvas.ui.canvas_bond_graphics_state import (
    CanvasBondGraphicsState,
    bond_items_for,
    set_bond_items_for,
)
from chemvas.ui.canvas_graph_state import CanvasGraphState
from chemvas.ui.canvas_group_state import CanvasGroupState
from chemvas.ui.canvas_mark_registry import CanvasMarkRegistry
from chemvas.ui.canvas_rotation_state import CanvasRotationState
from chemvas.ui.canvas_scene_items_state import (
    SCENE_ITEM_COLLECTION_ATTRS,
    CanvasSceneItemsState,
    scene_item_collection_for,
    set_scene_item_collection_for,
)
from chemvas.ui.canvas_smiles_input_state import (
    CanvasSmilesInputState,
    set_last_smiles_input_for,
)
from chemvas.ui.scene_clipboard_controller import (
    SceneClipboardController,
)
from chemvas.ui.scene_clipboard_state import SceneClipboardState
from chemvas.ui.scene_delete_controller import SceneDeleteController
from chemvas.ui.scene_transform_controller import SceneTransformController
from chemvas.ui.selection_style_state import SelectionStyleState


def _set_selectable(item: QGraphicsItem) -> QGraphicsItem:
    item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
    return item


def _make_rect_item(
    kind: str,
    *,
    data1=None,
    state: dict | None = None,
    rect: QRectF | None = None,
) -> QGraphicsRectItem:
    item = _set_selectable(QGraphicsRectItem(rect or QRectF(0.0, 0.0, 10.0, 10.0)))
    item.setData(0, kind)
    if data1 is not None:
        item.setData(1, data1)
    if state is not None:
        item.setData(9, dict(state))
        if kind == "mark":
            mark_data = dict(data1) if isinstance(data1, dict) else {}
            for key in ("atom_id", "dx", "dy", "text"):
                if key in state and key not in mark_data:
                    mark_data[key] = state.get(key)
            if "mark_kind" in state and "kind" not in mark_data:
                mark_data["kind"] = state.get("mark_kind")
            item.setData(1, mark_data)
            item.setPos(float(state.get("x", 0.0)), float(state.get("y", 0.0)))
    return item


def _make_note_item(text: str, x: float, y: float) -> QGraphicsTextItem:
    item = _set_selectable(QGraphicsTextItem(text))
    item.setData(0, "note")
    item.setData(9, {"kind": "note", "text": text, "x": x, "y": y})
    item.setPos(x, y)
    return item


def _make_ring_item() -> QGraphicsPolygonItem:
    polygon = QPolygonF([QPointF(0.0, 0.0), QPointF(12.0, 0.0), QPointF(6.0, 10.0)])
    item = _set_selectable(QGraphicsPolygonItem(polygon))
    item.setData(0, "ring")
    item.setData(9, {"kind": "ring", "points": [(0.0, 0.0), (12.0, 0.0), (6.0, 10.0)]})
    return item


def _make_model_ring_item(
    model: MoleculeModel,
    atom_ids: list[int],
    *,
    color: str,
    alpha: float,
) -> QGraphicsPolygonItem:
    points = [
        QPointF(model.atoms[atom_id].x, model.atoms[atom_id].y) for atom_id in atom_ids
    ]
    item = _set_selectable(QGraphicsPolygonItem(QPolygonF(points)))
    fill = QColor(color)
    fill.setAlphaF(alpha)
    item.setBrush(QBrush(fill))
    item.setData(0, "ring")
    item.setData(2, list(atom_ids))
    return item


def scene_clipboard_controller_for(canvas) -> SceneClipboardController:
    return SceneClipboardController(
        canvas,
        selection_controller=canvas.services.selection.selection_controller,
        bond_mutation_service=canvas.services.structure.canvas_bond_mutation_service,
    )


def scene_delete_controller_for(canvas) -> SceneDeleteController:
    return SceneDeleteController(
        canvas,
        move_controller=canvas.services.interaction.move_controller,
        atom_mutation_service=canvas.services.structure.canvas_atom_mutation_service,
        bond_mutation_service=canvas.services.structure.canvas_bond_mutation_service,
        style_controller=canvas.services.scene_operations.style_controller,
        history_service=canvas.history_service,
    )


def scene_transform_controller_for(canvas) -> SceneTransformController:
    return SceneTransformController(
        canvas,
        move_controller=canvas.services.interaction.move_controller,
        graph_service=canvas.services.graph_service,
        history_service=canvas.history_service,
    )


class _FakeSceneItemController:
    def __init__(self, canvas) -> None:
        self.canvas = canvas

    def remove_scene_item(self, item: QGraphicsItem) -> None:
        self.canvas.remove_scene_item(item)

    def create_scene_item_from_state(self, state: dict):
        return self.canvas.create_scene_item_from_state(state)

    def apply_scene_item_state(self, item: QGraphicsItem, state: dict) -> None:
        self.canvas.apply_scene_item_state(item, state)

    def attach_scene_item(self, item: QGraphicsItem) -> None:
        self.canvas.attach_scene_item(item)

    def restore_scene_item(self, item: QGraphicsItem) -> None:
        self.canvas.restore_scene_item(item)


class _FakeCanvas:
    CLIPBOARD_SELECTION_MIME = "application/x-chemvas-selection+json"
    CLIPBOARD_SELECTION_VERSION = 2

    def __init__(self) -> None:
        self._scene = QGraphicsScene()
        self.model = MoleculeModel()
        self.renderer = SimpleNamespace(
            style=SimpleNamespace(bond_length_px=20.0, bond_line_width=1.0)
        )
        # Bound to attributes as well as the runtime container: a test asserting
        # on the object it seeded fails if production mutated a different one.
        self.graph_state = CanvasGraphState()
        self.mark_registry = CanvasMarkRegistry()
        self.scene_clipboard_state = SceneClipboardState()
        self.runtime_state = canvas_runtime_state(
            atom_coords_3d_state=CanvasAtomCoords3DState(),
            atom_graphics_state=CanvasAtomGraphicsState(),
            bond_graphics_state=CanvasBondGraphicsState(),
            graph_state=self.graph_state,
            group_state=CanvasGroupState(),
            mark_registry=self.mark_registry,
            rotation_state=CanvasRotationState(),
            scene_clipboard_state=self.scene_clipboard_state,
            scene_items_state=CanvasSceneItemsState(),
            selection_style_state=SelectionStyleState(),
            smiles_input_state=CanvasSmilesInputState(),
        )
        set_last_smiles_input_for(self, None)
        for name in SCENE_ITEM_COLLECTION_ATTRS:
            set_scene_item_collection_for(self, name, [])
        self.scene_clipboard_state.paste_source_json = None
        self.scene_clipboard_state.paste_count = 0
        self._clipboard_payload = None
        self.delete_bond_calls: list[tuple[int, bool]] = []
        self.remove_bond_calls: list[int] = []
        self.redraw_connected_bonds_calls: list[int] = []
        self.remove_atom_calls: list[tuple[int, bool]] = []
        self.removed_scene_items: list[QGraphicsItem] = []
        self.pushed_commands: list[object] = []
        from chemvas.ui.history_operations import CanvasHistoryOperations

        self.history_service = SimpleNamespace(
            push=self.push_command, operations=CanvasHistoryOperations(self)
        )
        self.clear_handles_calls = 0
        set_atom_items_for(self, {})
        set_atom_dots_for(self, {})
        set_bond_items_for(self, {})
        self.created_scene_item_states: list[dict] = []
        self.created_items: list[QGraphicsItem] = []
        self.restore_bond_calls: list[tuple[int, dict]] = []
        self.selected_notes: list[QGraphicsTextItem] = []
        self.clear_note_selection_calls = 0
        self.update_selection_outline_calls = 0
        self.suspend_selection_outline_calls: list[bool] = []
        self.record_additions_calls: list[
            tuple[int, int, str | None, list[QGraphicsItem]]
        ] = []
        self.services = canvas_runtime_services(
            history_service=self.history_service,
            scene_item_controller=_FakeSceneItemController(self),
            graph_service=SimpleNamespace(
                connected_components=self.connected_components,
                bond_sets_for_atoms=lambda atom_ids: (
                    {
                        index
                        for index, bond in enumerate(self.model.bonds)
                        if bond is not None
                        and bond.a in atom_ids
                        and bond.b in atom_ids
                    },
                    {
                        index
                        for index, bond in enumerate(self.model.bonds)
                        if bond is not None
                        and ((bond.a in atom_ids) != (bond.b in atom_ids))
                    },
                ),
            ),
            atom_label_service=SimpleNamespace(
                add_or_update_atom_label=self.add_or_update_atom_label,
                position_label=self.position_label,
                # Same body as the real AtomLabelService.atom_item_for_id.
                atom_item_for_id=lambda atom_id: (
                    atom_items_for(self).get(atom_id)
                    or atom_dots_for(self).get(atom_id)
                ),
            ),
            canvas_atom_mutation_service=SimpleNamespace(
                add_atom=self.add_atom,
                remove_atom_only=self._remove_atom_only,
                restore_atom_from_state=self.restore_atom_from_state,
                apply_atom_color=self.apply_atom_color,
            ),
            canvas_bond_mutation_service=SimpleNamespace(
                add_bond=self.add_bond,
                restore_bond_from_state=self._restore_bond_from_state,
                remove_bond_by_id=self._remove_bond_by_id,
                trim_bonds_to_length=self._trim_bonds_to_length,
            ),
            scene_decoration_build_service=SimpleNamespace(
                set_mark_center=self.set_mark_center,
                # Inverse of this double's set_mark_center, which is what
                # serializing a mark's state reads back.
                mark_center=lambda item: item.pos(),
            ),
            hit_testing_service=SimpleNamespace(
                mark_spatial_index_dirty=self.mark_spatial_index_dirty
            ),
            canvas_ring_fill_scene_service=SimpleNamespace(
                update_ring_fills_for_atoms=lambda atom_ids, *, ring_items=None: None
            ),
            handle_overlay_service=SimpleNamespace(clear_handles=self.clear_handles),
            canvas_history_recording_service=SimpleNamespace(
                record_additions=self._record_additions
            ),
            selection_controller=SimpleNamespace(
                clear_note_selection=self.clear_note_selection,
                select_note=self.select_note,
                update_selection_outline=self.refresh_selection_outline,
            ),
            style_controller=SimpleNamespace(
                suspend_selection_outline=self.suspend_selection_outline
            ),
            move_controller=SimpleNamespace(
                redraw_connected_bonds=self.redraw_connected_bonds,
                redraw_bonds_for_atoms=self.redraw_bonds_for_atoms,
                move_atoms=self.move_atoms,
                move_item=self.move_item,
            ),
        )

    def devicePixelRatioF(self) -> float:
        return 1.0

    def scene(self) -> QGraphicsScene:
        return self._scene

    def _scene_items(self, name: str):
        return scene_item_collection_for(self, name)

    def _set_scene_items(self, name: str, value) -> None:
        set_scene_item_collection_for(self, name, value)

    selected_notes = property(
        lambda self: self._scene_items("selected_notes"),
        lambda self, value: self._set_scene_items("selected_notes", value),
    )
    ring_items = property(
        lambda self: self._scene_items("ring_items"),
        lambda self, value: self._set_scene_items("ring_items", value),
    )
    note_items = property(
        lambda self: self._scene_items("note_items"),
        lambda self, value: self._set_scene_items("note_items", value),
    )
    mark_items = property(
        lambda self: self._scene_items("mark_items"),
        lambda self, value: self._set_scene_items("mark_items", value),
    )
    arrow_items = property(
        lambda self: self._scene_items("arrow_items"),
        lambda self, value: self._set_scene_items("arrow_items", value),
    )
    ts_bracket_items = property(
        lambda self: self._scene_items("ts_bracket_items"),
        lambda self, value: self._set_scene_items("ts_bracket_items", value),
    )
    orbital_items = property(
        lambda self: self._scene_items("orbital_items"),
        lambda self, value: self._set_scene_items("orbital_items", value),
    )

    @property
    def atom_items(self):
        return atom_items_for(self)

    @atom_items.setter
    def atom_items(self, value) -> None:
        set_atom_items_for(self, value)

    @property
    def atom_dots(self):
        return atom_dots_for(self)

    @atom_dots.setter
    def atom_dots(self, value) -> None:
        set_atom_dots_for(self, value)

    @property
    def bond_items(self):
        return bond_items_for(self)

    @bond_items.setter
    def bond_items(self, value) -> None:
        set_bond_items_for(self, value)

    def add_item(self, item: QGraphicsItem, *, selected: bool = False) -> None:
        self._scene.addItem(item)
        if selected:
            item.setSelected(True)

    def delete_bond(self, bond_id: int, record: bool = True) -> None:
        self.delete_bond_calls.append((bond_id, record))
        if 0 <= bond_id < len(self.model.bonds):
            self.model.bonds[bond_id] = None

    def _bond_state_dict(self, bond: Bond) -> dict:
        return {
            "a": bond.a,
            "b": bond.b,
            "order": bond.order,
            "style": bond.style,
            "color": bond.color,
        }

    def _remove_bond_by_id(self, bond_id: int) -> None:
        self.remove_bond_calls.append(bond_id)
        self.model.bonds[bond_id] = None

    def _trim_bonds_to_length(self, length: int) -> None:
        del self.model.bonds[length:]

    def redraw_connected_bonds(
        self, atom_id: int, skip_bond_id: int | None = None
    ) -> None:
        self.redraw_connected_bonds_calls.append(atom_id)

    def redraw_bonds_for_atoms(self, atom_ids: set[int]) -> None:
        for atom_id in atom_ids:
            self.redraw_connected_bonds(atom_id)

    def mark_spatial_index_dirty(self) -> None:
        return None

    def _atom_state_dict(self, atom_id: int) -> dict:
        atom = self.model.atoms[atom_id]
        return {
            "element": atom.element,
            "x": atom.x,
            "y": atom.y,
            "color": atom.color,
            "explicit_label": atom.explicit_label,
        }

    def _remove_atom_only(self, atom_id: int, remove_marks: bool = True) -> None:
        self.remove_atom_calls.append((atom_id, remove_marks))
        self.model.atoms.pop(atom_id, None)
        atom_coords_3d_for(self).pop(atom_id, None)

    def scene_item_state(self, item: QGraphicsItem) -> dict:
        state = item.data(9)
        return dict(state) if isinstance(state, dict) else {}

    def remove_scene_item(self, item: QGraphicsItem) -> None:
        self.removed_scene_items.append(item)
        if item.data(0) == "ring" and item in self.ring_items:
            self.ring_items.remove(item)
        self._scene.removeItem(item)

    def attach_scene_item(self, item: QGraphicsItem) -> None:
        if item.data(0) == "ring" and item not in self.ring_items:
            self.ring_items.append(item)
        self.add_item(item)

    def restore_scene_item(self, item: QGraphicsItem) -> None:
        self.attach_scene_item(item)

    def clear_handles(self) -> None:
        self.clear_handles_calls += 1

    def suspend_selection_outline(self, suspended: bool) -> None:
        self.suspend_selection_outline_calls.append(bool(suspended))

    def refresh_selection_outline(self) -> None:
        self.update_selection_outline_calls += 1

    def move_atoms(
        self,
        atom_ids: set[int],
        dx: float,
        dy: float,
        bond_ids: set[int] | None = None,
        redraw_bond_ids: set[int] | None = None,
        update_selection: bool = True,
        rebuild_stale_bond_topology: bool = False,
    ) -> None:
        for atom_id in atom_ids:
            atom = self.model.atoms.get(atom_id)
            if atom is None:
                continue
            atom.x += dx
            atom.y += dy
        if update_selection:
            self.refresh_selection_outline()

    def move_item(
        self, item: QGraphicsItem, dx: float, dy: float, update_selection: bool = True
    ) -> None:
        item.moveBy(dx, dy)
        if update_selection:
            self.refresh_selection_outline()

    def push_command(self, command) -> None:
        self.pushed_commands.append(command)

    def new_mime_data(self, payload: bytes):
        from PyQt6.QtCore import QMimeData

        mime_data = QMimeData()
        mime_data.setData(self.CLIPBOARD_SELECTION_MIME, payload)
        return mime_data

    @staticmethod
    def new_image_mime_data(image: QImage):
        from PyQt6.QtCore import QMimeData

        mime_data = QMimeData()
        mime_data.setImageData(image)
        return mime_data

    def _clipboard_selection_payload(self):
        return self._clipboard_payload

    def _selected_items_for_transform(self):
        return list(self._scene.selectedItems())

    def _selection_items_for_copy(self):
        return list(self._scene.selectedItems())

    def _selected_atom_ids_for_transform(self) -> set[int]:
        atom_ids: set[int] = set()
        for item in self._scene.selectedItems():
            if item.data(0) == "atom" and isinstance(item.data(1), int):
                atom_ids.add(item.data(1))
        return atom_ids

    def connected_components(self, atom_ids: set[int]) -> list[set[int]]:
        return [set(atom_ids)] if atom_ids else []

    def _bounding_box_center_for_atoms(self, atom_ids: set[int]) -> QPointF | None:
        if not atom_ids:
            return None
        xs = [
            self.model.atoms[atom_id].x
            for atom_id in atom_ids
            if atom_id in self.model.atoms
        ]
        ys = [
            self.model.atoms[atom_id].y
            for atom_id in atom_ids
            if atom_id in self.model.atoms
        ]
        if not xs or not ys:
            return None
        return QPointF((min(xs) + max(xs)) / 2.0, (min(ys) + max(ys)) / 2.0)

    def _clipboard_paste_offset(
        self, step: int, bond_length_px: float
    ) -> tuple[float, float]:
        magnitude = max(18.0, bond_length_px * 0.35) * max(1, step)
        return magnitude, magnitude

    def add_atom(self, element: str, x: float, y: float) -> int:
        atom_id = self.model.add_atom(element, x, y)
        atom_item = _make_rect_item("atom", data1=atom_id)
        atom_item.setRect(QRectF(x - 2.0, y - 2.0, 4.0, 4.0))
        self.add_item(atom_item)
        self.atom_items[atom_id] = atom_item
        return atom_id

    def apply_atom_color(self, atom_id: int, color: str) -> None:
        self.model.atoms[atom_id].color = color

    def restore_atom_from_state(self, atom_id: int, state: dict) -> None:
        self.model.atoms[atom_id] = Atom(
            state.get("element", "C"),
            float(state.get("x", 0.0)),
            float(state.get("y", 0.0)),
            color=state.get("color", "#000000"),
            explicit_label=bool(state.get("explicit_label", False)),
        )

    def add_or_update_atom_label(
        self,
        atom_id: int,
        element: str,
        clear_smiles: bool = False,
        record: bool = False,
        allow_merge: bool = False,
        show_carbon: bool = False,
        literal_label: bool | None = None,
    ) -> None:
        self.model.atoms[atom_id].element = element
        self.model.atoms[atom_id].explicit_label = (
            show_carbon if literal_label is None else literal_label
        )

    def position_label(self, item: QGraphicsItem, x: float, y: float) -> None:
        set_rect = getattr(item, "setRect", None)
        if callable(set_rect):
            set_rect(QRectF(x - 2.0, y - 2.0, 4.0, 4.0))
            return
        item.setPos(x, y)

    def set_mark_center(self, item: QGraphicsItem, center: QPointF) -> None:
        item.setPos(center)
        state = item.data(9)
        if isinstance(state, dict):
            state = dict(state)
            state["x"] = center.x()
            state["y"] = center.y()
            item.setData(9, state)

    def add_bond(self, atom_a: int, atom_b: int, order: int) -> int:
        self.model.bonds.append(Bond(atom_a, atom_b, order))
        return len(self.model.bonds) - 1

    def _restore_bond_from_state(self, bond_id: int, state: dict) -> None:
        self.restore_bond_calls.append((bond_id, dict(state)))
        self.model.bonds[bond_id] = Bond(
            state["a"],
            state["b"],
            state.get("order", 1),
            state.get("style", "single"),
            state.get("color", "#000000"),
        )

    def _translated_scene_item_state(
        self,
        state: dict,
        *,
        dx: float,
        dy: float,
        atom_id_map: dict[int, int],
    ) -> dict | None:
        if not isinstance(state, dict):
            return None
        translated = dict(state)
        kind = translated.get("kind")
        if kind == "mark":
            atom_id = translated.get("atom_id")
            translated["atom_id"] = (
                atom_id_map.get(atom_id) if isinstance(atom_id, int) else None
            )
            translated["x"] = float(translated["x"]) + dx
            translated["y"] = float(translated["y"]) + dy
            return translated
        if kind == "note":
            translated["x"] = float(translated["x"]) + dx
            translated["y"] = float(translated["y"]) + dy
            return translated
        return translated

    def create_scene_item_from_state(self, state: dict):
        self.created_scene_item_states.append(dict(state))
        kind = state.get("kind")
        if kind == "note":
            item = _make_note_item(
                str(state.get("text", "")),
                float(state.get("x", 0.0)),
                float(state.get("y", 0.0)),
            )
        elif kind == "mark":
            item = _make_rect_item(
                "mark",
                data1={"atom_id": state.get("atom_id")},
                state=state,
                rect=QRectF(
                    float(state.get("x", 0.0)), float(state.get("y", 0.0)), 6.0, 6.0
                ),
            )
        else:
            item = _make_rect_item(kind or "item", state=state)
        self.created_items.append(item)
        self.add_item(item)
        return item

    def _atom_item_for_id(self, atom_id: int):
        return self.atom_items.get(atom_id)

    def clear_note_selection(self) -> None:
        self.clear_note_selection_calls += 1
        self.selected_notes.clear()

    def select_note(self, item: QGraphicsTextItem, additive: bool = True) -> None:
        self.selected_notes.append(item)

    def _record_additions(
        self,
        before_next_atom_id: int,
        before_bond_count: int,
        before_smiles_input: str | None,
        added_scene_items: list | None = None,
    ) -> None:
        self.record_additions_calls.append(
            (
                before_next_atom_id,
                before_bond_count,
                before_smiles_input,
                added_scene_items if added_scene_items is not None else [],
            )
        )

    @staticmethod
    def _bounds_from_points(points: list[QPointF]) -> QRectF | None:
        if not points:
            return None
        xs = [point.x() for point in points]
        ys = [point.y() for point in points]
        return QRectF(min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys))

    @staticmethod
    def _ts_bracket_rect_from_state(state: dict) -> QRectF | None:
        if not {"left", "top", "right", "bottom"} <= state.keys():
            return None
        return QRectF(
            float(state["left"]),
            float(state["top"]),
            float(state["right"]) - float(state["left"]),
            float(state["bottom"]) - float(state["top"]),
        )

    def set_atom_positions(
        self, positions: dict[int, tuple[float, float]], update_selection: bool = True
    ) -> None:
        for atom_id, (x, y) in positions.items():
            if atom_id in self.model.atoms:
                self.model.atoms[atom_id].x = x
                self.model.atoms[atom_id].y = y

    def apply_scene_item_state(self, item: QGraphicsItem, state: dict) -> None:
        item.setData(9, dict(state))

    @staticmethod
    def _flip_point(point: QPointF, center: QPointF, horizontal: bool) -> QPointF:
        if horizontal:
            return QPointF(center.x() - (point.x() - center.x()), point.y())
        return QPointF(point.x(), center.y() - (point.y() - center.y()))


class _RecordingFakeCanvas(_FakeCanvas):
    def __init__(self) -> None:
        super().__init__()
        self.atom_color_calls: list[tuple[int, str]] = []
        self.atom_label_calls: list[dict] = []
        self.select_note_calls: list[tuple[QGraphicsItem, bool]] = []
        self.translate_empty_kinds: set[str] = set()

    def apply_atom_color(self, atom_id: int, color: str) -> None:
        self.atom_color_calls.append((atom_id, color))
        super().apply_atom_color(atom_id, color)

    def add_or_update_atom_label(
        self,
        atom_id: int,
        element: str,
        clear_smiles: bool = False,
        record: bool = False,
        allow_merge: bool = False,
        show_carbon: bool = False,
        literal_label: bool | None = None,
    ) -> None:
        call = {
            "atom_id": atom_id,
            "element": element,
            "clear_smiles": clear_smiles,
            "record": record,
            "allow_merge": allow_merge,
        }
        if show_carbon:
            call["show_carbon"] = True
        if literal_label is not None:
            call["literal_label"] = literal_label
        self.atom_label_calls.append(call)
        super().add_or_update_atom_label(
            atom_id,
            element,
            clear_smiles=clear_smiles,
            record=record,
            allow_merge=allow_merge,
            show_carbon=show_carbon,
            literal_label=literal_label,
        )

    def select_note(self, item, additive: bool = True) -> None:
        self.select_note_calls.append((item, additive))
        super().select_note(item, additive=additive)

    def create_scene_item_from_state(self, state: dict):
        if isinstance(state, dict) and state.get("kind") in self.translate_empty_kinds:
            return None
        return super().create_scene_item_from_state(state)
