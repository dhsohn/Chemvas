from __future__ import annotations

from pathlib import Path

from core.document_io import read_document, write_document
from core.document_state import deserialize_model_state

from ui.canvas_document_export_access import export_canvas_scene_for
from ui.canvas_document_state import (
    apply_document_settings,
    restore_document_post_model_items,
    restore_document_pre_model_items,
    snapshot_canvas_document_state,
)
from ui.canvas_format_access import file_format_version_for
from ui.canvas_model_access import set_model_for
from ui.canvas_scene_reset_access import clear_scene_for
from ui.rdkit_adapter_access import (
    model_to_xyz_block_for,
    new_rdkit_adapter,
    preload_rdkit_for,
    rdkit_adapter_for,
    rdkit_is_loaded_for,
    rdkit_last_error_for,
)
from ui.renderer_style_access import (
    bond_length_pt_for,
    bond_length_px_for,
    bond_line_width_for,
)
from ui.selection_collection_access import selection_items_for_copy_for
from ui.structure_payload_access import build_3d_conversion_payload_for


class CanvasDocumentSessionService:
    def __init__(
        self,
        canvas,
        *,
        hit_testing_service,
        graph_service,
        structure_build_service=None,
        history_service=None,
    ) -> None:
        self.canvas = canvas
        self.history = history_service
        self.hit_testing_service = hit_testing_service
        self.graph_service = graph_service
        self.structure_build_service = structure_build_service

    def snapshot_state(self) -> dict:
        return snapshot_canvas_document_state(self.canvas)

    def apply_state(self, state: dict) -> None:
        if self.structure_build_service is None:
            raise RuntimeError("structure_build_service is required to apply document state")
        self.history.set_enabled(False)
        try:
            clear_scene_for(self.canvas)
            apply_document_settings(self.canvas, state)
            set_model_for(self.canvas, deserialize_model_state(state["model"]))
            self.graph_service.rebuild_bond_adjacency()
            restore_document_pre_model_items(self.canvas, state)
            self.structure_build_service.render_model()
            restore_document_post_model_items(self.canvas, state)
            self.hit_testing_service.mark_spatial_index_dirty()
        finally:
            self.history.set_enabled(True)

    def restore_state(self, state: dict) -> None:
        self.apply_state(state)
        self.history.clear()

    def save_to_file(self, path: str) -> None:
        write_document(path, self.snapshot_state(), file_format_version_for(self.canvas))

    def load_from_file(self, path: str) -> None:
        document = read_document(path)
        self.restore_state(document.state)

    def export_xyz(self, path: str) -> None:
        export_model, atom_annotations = build_3d_conversion_payload_for(self.canvas)
        xyz_block = model_to_xyz_block_for(self.canvas, export_model, atom_annotations=atom_annotations)
        if xyz_block is None:
            message = rdkit_last_error_for(self.canvas) or "Failed to export 3D XYZ."
            raise ValueError(message)
        Path(path).write_text(xyz_block, encoding="utf-8")

    def export_xyz_async(self, path: str, *, on_success, on_error) -> None:
        try:
            export_model, atom_annotations = build_3d_conversion_payload_for(self.canvas)
        except Exception as exc:
            on_error(str(exc) or "Failed to export 3D XYZ.")
            return
        if not rdkit_is_loaded_for(self.canvas) and not preload_rdkit_for(self.canvas):
            on_error(rdkit_last_error_for(self.canvas) or "RDKit is not available in this environment.")
            return

        from ui.rdkit_async_jobs import export_xyz_in_thread

        export_xyz_in_thread(
            self.canvas,
            rdkit_adapter=rdkit_adapter_for(self.canvas),
            model=export_model,
            atom_annotations=atom_annotations,
            path=path,
            on_success=on_success,
            on_error=on_error,
            rdkit_adapter_factory=new_rdkit_adapter,
        )

    def export_figure(
        self,
        path: str,
        *,
        fmt: str = "svg",
        scope: str = "sheet",
        dpi: int = 300,
        background: str = "transparent",
        sizing: str = "bond",
    ) -> None:
        from ui.export_plan_logic import points_for_mm

        pad = max(2.0, bond_line_width_for(self.canvas) * 2.0)
        items = None
        if scope == "selection":
            items = selection_items_for_copy_for(self.canvas)
            if not items:
                raise ValueError("Select something to export, or choose Whole sheet.")

        unit_scale = 1.0
        target_width_pt = None
        if sizing == "bond":
            bond_length_px = bond_length_px_for(self.canvas)
            if bond_length_px > 0:
                unit_scale = bond_length_pt_for(self.canvas) / bond_length_px
        elif sizing == "col1":
            target_width_pt = points_for_mm(84.0)
        elif sizing == "col2":
            target_width_pt = points_for_mm(174.0)

        export_canvas_scene_for(
            self.canvas,
            path,
            fmt=fmt,
            items=items,
            margin=pad,
            dpi=dpi,
            background=background,
            title="Chemvas drawing",
            unit_scale=unit_scale,
            target_width_pt=target_width_pt,
        )


__all__ = ["CanvasDocumentSessionService"]
