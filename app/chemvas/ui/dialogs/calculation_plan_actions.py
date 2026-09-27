"""Window-level operations on the active canvas's calculation plan and its panel."""

from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, cast

from chemvas.domain.document import (
    deserialize_model_state,
)
from chemvas.ui.canvas.canvas_calculation_plan_state import (
    calculation_plan_for,
    set_calculation_plan_for,
)
from chemvas.ui.canvas.canvas_window_access import history_service_for_canvas
from chemvas.ui.history.history_commands import SetCalculationPlanCommand
from chemvas.ui.transactions.document import document_transaction
from chemvas.ui.window.main_window_ports import active_canvas_for_window

if TYPE_CHECKING:
    from chemvas.domain.chemistry_types import RDKitResult
    from chemvas.ui.dialogs.calculation_step_widgets import (
        _CorrespondenceSuggester,
    )
    from chemvas.ui.window.main_window_like import MainWindowLike


def correspondence_suggester_for(
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


def save_calculation_plan_for_window(
    window: MainWindowLike, plan_state: dict[str, object]
) -> bool:
    canvas = active_canvas_for_window(window)
    current_plan = calculation_plan_for(canvas)
    if current_plan == plan_state:
        return False
    history = history_service_for_canvas(canvas)
    command = SetCalculationPlanCommand(current_plan, plan_state)
    with document_transaction(canvas, history_service=history):
        set_calculation_plan_for(canvas, plan_state)
        if not history.push(command):
            raise RuntimeError(
                "The calculation plan edit could not be recorded for Undo."
            )
    services = window.services
    services.canvas_document_service.refresh_tab_title(window, canvas)
    services.status_service.refresh_status_context(window)
    return True


def open_calculation_panel_for_window(window: MainWindowLike) -> None:
    from PyQt6.QtCore import Qt

    from chemvas.ui.dialogs.calculation_panel import CalculationPanel

    panel = window.ui_references.calculation_panel
    if panel is None:
        panel = CalculationPanel(window)
        window.ui_references.calculation_panel = panel
        window.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, panel)
        window.resizeDocks([panel], [420], Qt.Orientation.Horizontal)
        action = window.ui_references.reaction_mapping_action
        if action is not None:
            panel.visibilityChanged.connect(action.setChecked)
        panel.reload_drawing()
    panel.show()
    panel.raise_()


__all__ = [
    "correspondence_suggester_for",
    "open_calculation_panel_for_window",
    "save_calculation_plan_for_window",
]
