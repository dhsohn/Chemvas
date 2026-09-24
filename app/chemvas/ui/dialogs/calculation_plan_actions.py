"""Window-level entry point that edits the active canvas's calculation plan."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import TYPE_CHECKING, Any, cast

from PyQt6.QtWidgets import (
    QDialog,
    QMessageBox,
)

from chemvas.domain.document import (
    deserialize_model_state,
)
from chemvas.domain.document.inspection import inspect_components
from chemvas.ui.canvas.canvas_calculation_plan_state import (
    calculation_plan_for,
    set_calculation_plan_for,
)
from chemvas.ui.canvas.canvas_window_access import history_service_for_canvas
from chemvas.ui.dialogs.calculation_mapping_highlight import (
    CalculationMappingHighlighter,
)
from chemvas.ui.dialogs.calculation_step_dialog import CalculationStepDialog
from chemvas.ui.history.history_commands import SetCalculationPlanCommand
from chemvas.ui.transactions.document import document_transaction
from chemvas.ui.window.main_window_ports import (
    active_canvas_for_window,
    document_session_service_for_window,
)

if TYPE_CHECKING:
    from chemvas.domain.chemistry_types import RDKitResult
    from chemvas.ui.dialogs.calculation_step_widgets import (
        _CorrespondenceSuggester,
    )
    from chemvas.ui.window.main_window_like import MainWindowLike


def _correspondence_suggester_for(
    canvas: Any, document_state: Mapping[str, object]
) -> _CorrespondenceSuggester | None:
    raw_model = document_state.get("model")
    if not isinstance(raw_model, Mapping):
        return None
    model = deserialize_model_state(cast("Mapping[str, object]", raw_model))

    def suggest(
        reactant_atom_ids: frozenset[int],
        product_atom_ids: frozenset[int],
        existing_correspondence: Mapping[int, int],
    ) -> RDKitResult[list[tuple[int, int]]]:
        return canvas.rdkit.suggest_atom_correspondence_result(
            model, reactant_atom_ids, product_atom_ids, existing_correspondence
        )

    return suggest


def edit_calculation_plan_for_window(
    window: MainWindowLike,
    *,
    dialog_factory: Callable[..., CalculationStepDialog] = CalculationStepDialog,
) -> bool:
    canvas = active_canvas_for_window(window)
    document_state = document_session_service_for_window(window).snapshot_state()
    current_plan = calculation_plan_for(canvas)
    if current_plan is not None and "calculation_plan" not in document_state:
        QMessageBox.warning(
            window,
            "Calculation plan needs its original structures",
            "The drawing no longer matches the existing calculation plan. "
            "Its steps have been kept in this window. Undo the structure change "
            "before editing the plan, or attach a repaired plan using chemvas attach-plan. "
            "No calculation steps have been replaced.",
        )
        return False
    if not inspect_components(document_state):
        QMessageBox.information(
            window,
            "No structure",
            "Draw the reactant, product, catalyst, or spectator structures first.",
        )
        return False
    mapping_highlighter = CalculationMappingHighlighter(canvas)
    correspondence_suggester = _correspondence_suggester_for(canvas, document_state)
    try:
        dialog = dialog_factory(
            document_state,
            parent=window,
            mapping_highlighter=mapping_highlighter,
            correspondence_suggester=correspondence_suggester,
        )
        dialog_result = dialog.exec()
    finally:
        mapping_highlighter.clear_all()
    if dialog_result != QDialog.DialogCode.Accepted:
        return False
    if dialog.result_plan_state is None:
        raise RuntimeError("Accepted calculation dialog did not return a plan.")
    if current_plan == dialog.result_plan_state:
        return False
    history = history_service_for_canvas(canvas)
    command = SetCalculationPlanCommand(current_plan, dialog.result_plan_state)
    with document_transaction(canvas, history_service=history):
        set_calculation_plan_for(canvas, dialog.result_plan_state)
        if not history.push(command):
            raise RuntimeError(
                "The calculation plan edit could not be recorded for Undo."
            )
    services = window.services
    services.canvas_document_service.refresh_tab_title(window, canvas)
    services.status_service.refresh_status_context(window)
    return True


__all__ = [
    "edit_calculation_plan_for_window",
]
