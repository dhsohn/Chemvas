from __future__ import annotations
from typing import TYPE_CHECKING

from PyQt6.QtCore import QMimeData, QRectF, Qt
from PyQt6.QtGui import QImage, QPainter
from PyQt6.QtWidgets import QApplication, QGraphicsItem, QGraphicsPolygonItem, QGraphicsTextItem

from core.history import CompositeCommand, HistoryCommand
from ui.scene_delete_apply_logic import apply_delete_selection_plan
from ui.scene_clipboard_logic import (
    build_selection_clipboard_payload,
    clipboard_payload_candidates,
    decode_clipboard_selection_payload,
)
from ui.scene_clipboard_transaction_logic import (
    build_clipboard_copy_plan,
    build_clipboard_paste_plan,
    clipboard_copy_cache_values,
    visible_items_to_hide_for_copy,
)
from ui.bond_graphics_logic import refresh_bond_graphics
from ui.scene_delete_logic import build_delete_selection_plan, classify_delete_selection
from ui.scene_paste_apply_logic import apply_paste_payload
from ui.scene_single_item_mutation_logic import (
    apply_bond_style_with_history,
    cycle_bond_style_with_history,
    delete_atom_with_history,
    delete_bond_with_history,
    delete_ring_with_history,
    flip_bond_direction_with_history,
)
from ui.scene_transform_apply_logic import (
    apply_component_flip_transform,
    apply_standalone_flip_transform,
)
from ui.scene_transform_logic import (
    build_flip_atom_position_maps,
    center_for_flip_group,
    flip_bounds_for_item,
    flip_center_for_selection,
    flip_scene_item_state,
    group_items_for_flip_transform,
)
from ui.scene_item_access import (
    apply_scene_item_state as apply_scene_item_state_helper,
    create_scene_item_from_state as create_scene_item_from_state_helper,
    remove_scene_item as remove_scene_item_helper,
)

if TYPE_CHECKING:
    from ui.canvas_view import CanvasView


class SceneOpsController:
    def __init__(self, canvas: CanvasView) -> None:
        self.canvas = canvas

    def _remove_scene_item(self, item) -> None:
        remove_scene_item_helper(self.canvas, item)

    def _apply_scene_item_state(self, item, state: dict) -> None:
        apply_scene_item_state_helper(self.canvas, item, state)

    def _create_scene_item_from_state(self, state: dict):
        return create_scene_item_from_state_helper(self.canvas, state)

    def _rebuild_bond_graphics(self, bond_id: int, *, redraw_connected: bool) -> None:
        refresh_bond_graphics(
            bond_id,
            bonds=self.canvas.model.bonds,
            bond_items=self.canvas.bond_items,
            remove_scene_item=self.canvas.scene().removeItem,
            add_bond_graphics=self.canvas._add_bond_graphics,
            redraw_connected=redraw_connected,
            redraw_connected_bonds=lambda atom_id, skip_bond_id: self.canvas._redraw_connected_bonds(
                atom_id,
                skip_bond_id=skip_bond_id,
            ),
        )

    def delete_atom(self, atom_id: int, record: bool = True) -> HistoryCommand | None:
        if not isinstance(atom_id, int) or atom_id not in self.canvas.model.atoms:
            return None
        before_smiles_input = self.canvas.last_smiles_input
        command = delete_atom_with_history(
            atom_id,
            bonds=self.canvas.model.bonds,
            marks_by_atom=self.canvas._marks_by_atom,
            before_smiles_input=before_smiles_input,
            current_smiles_input_getter=lambda: self.canvas.last_smiles_input,
            clear_smiles_input=lambda: setattr(self.canvas, "last_smiles_input", None),
            mark_state_getter=self.canvas._mark_state_dict,
            bond_state_getter=self.canvas._bond_state_dict,
            remove_bond_by_id=self.canvas._remove_bond_by_id,
            redraw_connected_bonds=self.canvas._redraw_connected_bonds,
            atom_state_getter=self.canvas._atom_state_dict,
            next_atom_id_getter=lambda: self.canvas.model.next_atom_id,
            remove_atom_only=self.canvas._remove_atom_only,
        )
        if record:
            self.canvas._push_command(command)
        return command

    def delete_bond(self, bond_id: int, record: bool = True) -> HistoryCommand | None:
        if not isinstance(bond_id, int):
            return None
        before_smiles_input = self.canvas.last_smiles_input
        command = delete_bond_with_history(
            bond_id,
            bonds=self.canvas.model.bonds,
            before_smiles_input=before_smiles_input,
            current_smiles_input_getter=lambda: self.canvas.last_smiles_input,
            clear_smiles_input=lambda: setattr(self.canvas, "last_smiles_input", None),
            bond_state_getter=self.canvas._bond_state_dict,
            remove_bond_by_id=self.canvas._remove_bond_by_id,
            redraw_connected_bonds=self.canvas._redraw_connected_bonds,
        )
        if command is None:
            return None
        if record:
            self.canvas._push_command(command)
        return command

    def delete_ring(self, item: QGraphicsPolygonItem, record: bool = True) -> HistoryCommand | None:
        command = delete_ring_with_history(
            item,
            ring_state_getter=self.canvas._ring_state_dict,
            remove_scene_item=self._remove_scene_item,
        )
        if record:
            self.canvas._push_command(command)
        return command

    def delete_selected_items(self) -> bool:
        items = self.canvas.scene().selectedItems()
        if not items:
            return False
        suspend_selection_outline = getattr(self.canvas, "suspend_selection_outline", None)
        refresh_selection_outline = getattr(self.canvas, "_update_selection_outline", None)
        if callable(suspend_selection_outline):
            suspend_selection_outline(True)
        try:
            selection = classify_delete_selection(items)
            plan = build_delete_selection_plan(
                selection,
                bonds=self.canvas.model.bonds,
                marks_by_atom=self.canvas._marks_by_atom,
                mark_state_getter=self.canvas._mark_state_dict,
            )

            if plan.single_bond_id is not None:
                self.delete_bond(plan.single_bond_id, record=True)
                return True

            before_smiles_input = self.canvas.last_smiles_input
            if plan.clear_smiles_input:
                self.canvas.last_smiles_input = None
            commands = apply_delete_selection_plan(
                plan,
                bonds=self.canvas.model.bonds,
                before_smiles_input=before_smiles_input,
                current_smiles_input_getter=lambda: self.canvas.last_smiles_input,
                bond_state_getter=self.canvas._bond_state_dict,
                remove_bond_by_id=self.canvas._remove_bond_by_id,
                redraw_connected_bonds=self.canvas._redraw_connected_bonds,
                atom_state_getter=self.canvas._atom_state_dict,
                next_atom_id_getter=lambda: self.canvas.model.next_atom_id,
                remove_atom_only=self.canvas._remove_atom_only,
                scene_item_state_getter=self.canvas.scene_item_state,
                remove_scene_item=self._remove_scene_item,
                clear_handles=self.canvas.clear_handles,
            )

            if not commands:
                return False
            if len(commands) == 1:
                self.canvas._push_command(commands[0])
                return True
            self.canvas._push_command(CompositeCommand(commands))
            return True
        finally:
            if callable(suspend_selection_outline):
                suspend_selection_outline(False)
            if callable(refresh_selection_outline):
                refresh_selection_outline()

    def flip_bond_direction(self, bond_id: int) -> None:
        flip_bond_direction_with_history(
            bond_id,
            bonds=self.canvas.model.bonds,
            before_smiles_input=self.canvas.last_smiles_input,
            current_smiles_input_getter=lambda: self.canvas.last_smiles_input,
            bond_state_getter=self.canvas._bond_state_dict,
            rebuild_bond_graphics=self._rebuild_bond_graphics,
            record_bond_update=self.canvas._record_bond_update,
        )

    def apply_bond_style(self, bond_id: int, style: str, order: int) -> None:
        apply_bond_style_with_history(
            bond_id,
            bonds=self.canvas.model.bonds,
            style=style,
            order=order,
            before_smiles_input=self.canvas.last_smiles_input,
            current_smiles_input_getter=lambda: self.canvas.last_smiles_input,
            bond_state_getter=self.canvas._bond_state_dict,
            rebuild_bond_graphics=self._rebuild_bond_graphics,
            record_bond_update=self.canvas._record_bond_update,
        )

    def cycle_bond_style(self, bond_id: int) -> None:
        cycle_bond_style_with_history(
            bond_id,
            bonds=self.canvas.model.bonds,
            before_smiles_input=self.canvas.last_smiles_input,
            current_smiles_input_getter=lambda: self.canvas.last_smiles_input,
            bond_state_getter=self.canvas._bond_state_dict,
            rebuild_bond_graphics=self._rebuild_bond_graphics,
            record_bond_update=self.canvas._record_bond_update,
        )

    def _selected_atom_components_for_transform(self, atom_ids: set[int]) -> list[set[int]]:
        if not atom_ids:
            return []
        component_key = (frozenset(atom_ids), self.canvas._graph_version)
        if component_key != self.canvas._selection_component_cache_signature:
            self.canvas._selection_component_cache_signature = component_key
            self.canvas._selection_component_cache = self.canvas._connected_components(atom_ids)
        return [set(component) for component in self.canvas._selection_component_cache]

    def flip_selected_items(self, horizontal: bool) -> None:
        items = self.canvas._selected_items_for_transform()
        atom_ids = self.canvas._selected_atom_ids_for_transform()
        if not atom_ids and not items:
            return

        commands: list[HistoryCommand] = []
        atom_components = self._selected_atom_components_for_transform(atom_ids)
        groups = group_items_for_flip_transform(
            items,
            atom_components=atom_components,
            marks_by_atom=self.canvas._marks_by_atom,
        )

        def flip_bounds(item):
            return flip_bounds_for_item(
                item,
                scene_item_state_getter=self.canvas.scene_item_state,
                bounds_from_points=self.canvas._bounds_from_points,
            )

        def flip_center(selected_atom_ids, selected_items):
            return flip_center_for_selection(
                selected_atom_ids,
                selected_items,
                atoms=self.canvas.model.atoms,
                flip_bounds_getter=flip_bounds,
            )

        def flip_state(item, before_state, center, is_horizontal, transformed):
            return flip_scene_item_state(
                item,
                before_state,
                center=center,
                horizontal=is_horizontal,
                transformed_atom_positions=transformed,
                atoms=self.canvas.model.atoms,
                flip_point=self.canvas._flip_point,
                ts_bracket_rect_from_state=self.canvas._ts_bracket_rect_from_state,
            )

        for component, component_items in zip(atom_components, groups.component_items):
            center = center_for_flip_group(
                component,
                component_items,
                bounding_box_center_for_atoms=self.canvas._bounding_box_center_for_atoms,
                flip_center_for_selection_getter=flip_center,
            )
            if center is None:
                continue
            position_maps = build_flip_atom_position_maps(
                sorted(component),
                atoms=self.canvas.model.atoms,
                center=center,
                flip_point=lambda point, pivot: self.canvas._flip_point(point, pivot, horizontal),
            )
            commands.extend(
                apply_component_flip_transform(
                    component_items=component_items,
                    scene_item_state_getter=self.canvas.scene_item_state,
                    position_maps=position_maps,
                    center=center,
                    horizontal=horizontal,
                    flip_state_getter=flip_state,
                    set_atom_positions=self.canvas.set_atom_positions,
                    apply_scene_item_state=self._apply_scene_item_state,
                )
            )

        for item in groups.standalone_items:
            center = center_for_flip_group(
                set(),
                [item],
                bounding_box_center_for_atoms=self.canvas._bounding_box_center_for_atoms,
                flip_center_for_selection_getter=flip_center,
            )
            if center is None:
                continue
            command = apply_standalone_flip_transform(
                item,
                scene_item_state_getter=self.canvas.scene_item_state,
                center=center,
                horizontal=horizontal,
                flip_state_getter=flip_state,
                apply_scene_item_state=self._apply_scene_item_state,
            )
            if command is None:
                continue
            commands.append(command)

        if not commands:
            return
        self.canvas._update_selection_outline()
        if len(commands) == 1:
            self.canvas._push_command(commands[0])
            return
        self.canvas._push_command(CompositeCommand(commands))

    def _selection_payload_for_clipboard(self) -> dict | None:
        selected_items = self.canvas._selected_items_for_transform()
        explicit_atom_ids, bond_ids = self.canvas._selected_ids()
        return build_selection_clipboard_payload(
            selected_items=selected_items,
            explicit_atom_ids=explicit_atom_ids,
            selected_bond_ids=bond_ids,
            bonds=self.canvas.model.bonds,
            ring_items=self.canvas.ring_items,
            marks_by_atom=self.canvas._marks_by_atom,
            scene=self.canvas.scene(),
            atom_state_getter=self.canvas._atom_state_dict,
            bond_state_getter=self.canvas._bond_state_dict,
            scene_item_state_getter=self.canvas.scene_item_state,
            version=self.canvas.CLIPBOARD_SELECTION_VERSION,
        )

    def _clipboard_selection_payload(self) -> tuple[dict | None, str | None]:
        mime_data = QApplication.clipboard().mimeData()
        payload_candidates = clipboard_payload_candidates(
            mime_data,
            mime_type=self.canvas.CLIPBOARD_SELECTION_MIME,
            cached_payload_json=self.canvas._clipboard_selection_payload_json,
        )
        return decode_clipboard_selection_payload(
            payload_candidates,
            version=self.canvas.CLIPBOARD_SELECTION_VERSION,
        )

    def _select_pasted_content(self, atom_ids: set[int], scene_items: list[QGraphicsItem]) -> None:
        self.canvas.scene().blockSignals(True)
        try:
            self.canvas.scene().clearSelection()
        finally:
            self.canvas.scene().blockSignals(False)
        self.canvas.clear_note_selection()
        for atom_id in atom_ids:
            atom_item = self.canvas._atom_item_for_id(atom_id)
            if atom_item is not None:
                atom_item.setSelected(True)
        for item in scene_items:
            if item is None:
                continue
            if item.data(0) == "note" and isinstance(item, QGraphicsTextItem):
                self.canvas.select_note(item, additive=True)
            item.setSelected(True)
        self.canvas._update_selection_outline()

    def copy_selection_to_clipboard(self) -> bool:
        items = self.canvas._selection_items_for_copy()
        if not items:
            return False
        payload = self._selection_payload_for_clipboard()
        plan = build_clipboard_copy_plan(
            items,
            payload=payload,
            bond_line_width=self.canvas.renderer.style.bond_line_width,
            device_pixel_ratio=(
                float(self.canvas.devicePixelRatioF())
                if hasattr(self.canvas, "devicePixelRatioF")
                else 1.0
            ),
        )
        if plan is None:
            return False
        hidden = visible_items_to_hide_for_copy(
            self.canvas.scene().items(plan.source),
            selected_items=set(items),
        )
        for item in hidden:
            item.setVisible(False)
        try:
            image = QImage(plan.image_width, plan.image_height, QImage.Format.Format_ARGB32_Premultiplied)
            image.setDevicePixelRatio(plan.scale)
            image.fill(Qt.GlobalColor.transparent)
            painter = QPainter(image)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
            self.canvas.scene().render(
                painter,
                QRectF(0, 0, plan.source.width(), plan.source.height()),
                plan.source,
            )
            painter.end()
        finally:
            for item in hidden:
                item.setVisible(True)
        mime_data = QMimeData()
        mime_data.setImageData(image)
        if plan.payload_json is not None:
            mime_data.setData(self.canvas.CLIPBOARD_SELECTION_MIME, plan.payload_json.encode("utf-8"))
        (
            self.canvas._clipboard_selection_payload_json,
            self.canvas._clipboard_paste_source_json,
            self.canvas._clipboard_paste_count,
        ) = clipboard_copy_cache_values(plan.payload_json)
        QApplication.clipboard().setMimeData(mime_data)
        return True

    def paste_selection_from_clipboard(self) -> bool:
        payload, payload_json = self._clipboard_selection_payload()
        plan = build_clipboard_paste_plan(
            payload=payload,
            payload_json=payload_json,
            previous_source_json=self.canvas._clipboard_paste_source_json,
            previous_paste_count=self.canvas._clipboard_paste_count,
            bond_length_px=self.canvas.renderer.style.bond_length_px,
            clipboard_paste_offset=self.canvas._clipboard_paste_offset,
            before_next_atom_id=self.canvas.model.next_atom_id,
            before_bond_count=len(self.canvas.model.bonds),
            before_smiles_input=self.canvas.last_smiles_input,
        )
        if plan is None:
            return False
        self.canvas._clipboard_paste_source_json = plan.paste_source_json
        self.canvas._clipboard_paste_count = plan.paste_count
        if not plan.has_payload_content():
            return False

        result = apply_paste_payload(
            atoms=plan.atoms,
            bonds=plan.bonds,
            rings=plan.rings,
            marks=plan.marks,
            scene_items=plan.scene_items,
            dx=plan.dx,
            dy=plan.dy,
            add_atom=self.canvas.add_atom,
            apply_atom_color=self.canvas.apply_atom_color,
            add_or_update_atom_label=self.canvas.add_or_update_atom_label,
            add_bond=self.canvas.add_bond,
            restore_bond_from_state=self.canvas._restore_bond_from_state,
            translated_scene_item_state=self.canvas._translated_scene_item_state,
            create_scene_item_from_state=self._create_scene_item_from_state,
        )

        if not result.has_changes():
            return False

        self._select_pasted_content(result.new_atom_ids, result.added_scene_items)
        self.canvas._record_additions(
            plan.before_next_atom_id,
            plan.before_bond_count,
            plan.before_smiles_input,
            added_scene_items=result.added_scene_items,
        )
        return True


__all__ = ["SceneOpsController"]
