from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any, Protocol, cast

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QInputMethodEvent
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from chemvas.domain.document import (
    CalculationAtomCorrespondence,
    CalculationEndpointRole,
    CalculationState,
    CalculationStateMember,
    CalculationStep,
    CalculationStepEndpoint,
    calculation_plan_to_state,
    deserialize_model_state,
)
from chemvas.features.calculation_bundle import (
    calculation_state_by_id,
    correspondence_readiness,
    identity_correspondence,
    included_atom_ids,
    inspect_components,
    plan_with_replaced_step,
    structural_calculation_plan_for_document,
)
from chemvas.ui.calculation_mapping_highlight import CalculationMappingHighlighter
from chemvas.ui.canvas_calculation_plan_state import set_calculation_plan_for
from chemvas.ui.main_window_ports import (
    active_canvas_for_window,
    document_session_service_for_window,
    services_for_window,
)

_UNUSED = "unused"


@dataclass(frozen=True)
class _EndpointWidgets:
    state_id: QLineEdit
    charge: QSpinBox
    multiplicity: QSpinBox


class _MappingHighlighter(Protocol):
    def show_mapping(
        self,
        reactant_atom_id: int,
        product_atom_id: int | None,
    ) -> None: ...

    def clear(self) -> None: ...


class _CorrespondenceSuggester(Protocol):
    def __call__(
        self,
        reactant_atom_ids: frozenset[int],
        product_atom_ids: frozenset[int],
    ) -> list[tuple[int, int]]: ...


class _NoInputMethodTableWidget(QTableWidget):
    """Table that ignores input-method composition outright.

    Neither dialog table takes text input: cells are read-only items or
    persistent combo widgets. QAbstractItemView still reacts to a
    QInputMethodEvent by starting or focusing an editor for the current
    cell, and for cells hosting a widget, edit() focuses that widget
    before consulting the edit triggers — so NoEditTriggers alone does
    not stop it. On Wayland (WSLg) each such focus change makes the
    text-input integration re-deliver the composition event, and the
    mutual recursion overflows the C stack; an active Korean IME crashed
    the app this way twice. Dropping the event here removes the app-side
    entry point of that recursion for every cell kind.
    """

    def inputMethodEvent(self, event: QInputMethodEvent | None) -> None:
        if event is not None:
            event.ignore()


class _MappingProductCombo(QComboBox):
    popup_closed = pyqtSignal()

    def hidePopup(self) -> None:
        super().hidePopup()
        self.popup_closed.emit()


class CalculationStepDialog(QDialog):
    def __init__(
        self,
        document_state: dict[str, object],
        *,
        parent: QWidget | None = None,
        mapping_highlighter: _MappingHighlighter | None = None,
        correspondence_suggester: _CorrespondenceSuggester | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Calculation States and Elementary Step")
        self.resize(1080, 760)
        self._document_state = document_state
        self._mapping_highlighter = mapping_highlighter
        self._correspondence_suggester = correspondence_suggester
        self._components = inspect_components(document_state)
        raw_model = document_state.get("model")
        if not isinstance(raw_model, Mapping):
            raise ValueError("Invalid Chemvas document state: model is missing.")
        model = deserialize_model_state(cast(Mapping[str, object], raw_model))
        self._atom_elements = {
            atom_id: atom.element for atom_id, atom in model.atoms.items()
        }
        self._component_index_by_atom = {
            atom_id: component.index
            for component in self._components
            for atom_id in component.atom_ids
        }
        self._plan = (
            structural_calculation_plan_for_document(document_state)
            if document_state.get("calculation_plan") is not None
            else None
        )
        self.result_plan_state: dict[str, object] | None = None
        self._loading = False
        self._inclusion_combos: dict[tuple[str, int], QComboBox] = {}
        self._role_combos: dict[tuple[str, int], QComboBox] = {}
        self._mapping_by_reactant: dict[int, int | None] = {}
        self._mapping_combos: dict[int, QComboBox] = {}
        self._mapping_row_by_reactant: dict[int, int] = {}

        layout = QVBoxLayout(self)
        explanation = QLabel(
            "Assign every drawn connected component to each endpoint. Included "
            "members enter the ORCA geometry; context-only members are recorded "
            "without entering coordinates or electron counts."
        )
        explanation.setWordWrap(True)
        layout.addWidget(explanation)

        self.step_selector = QComboBox(self)
        self.step_selector.addItem("New step", None)
        if self._plan is not None:
            for step in self._plan.steps:
                self.step_selector.addItem(f"Edit {step.id}", step.id)
        selector_form = QFormLayout()
        selector_form.addRow("Mode", self.step_selector)
        layout.addLayout(selector_form)

        fields = QHBoxLayout()
        self.step_id = QLineEdit(self)
        step_form = QFormLayout()
        step_form.addRow("Step ID", self.step_id)
        fields.addLayout(step_form)
        self.reactant_widgets = self._endpoint_fields("Reactant", fields)
        self.product_widgets = self._endpoint_fields("Product", fields)
        layout.addLayout(fields)

        self.table = _NoInputMethodTableWidget(len(self._components), 6, self)
        # Cells hosting widgets have no item, so the model reports the default
        # editable flags; direct cell editing stays disabled so no phantom item
        # editor can open (composition input is handled by the table class).
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setHorizontalHeaderLabels(
            (
                "Component",
                "Chemvas atom IDs",
                "Reactant inclusion",
                "Reactant role",
                "Product inclusion",
                "Product role",
            )
        )
        vertical_header = self.table.verticalHeader()
        if vertical_header is not None:
            vertical_header.setVisible(False)
        horizontal_header = self.table.horizontalHeader()
        if horizontal_header is not None:
            horizontal_header.setStretchLastSection(True)
        self._populate_component_rows()
        layout.addWidget(self.table)

        mapping_heading = QLabel("Atom correspondence", self)
        mapping_heading.setStyleSheet("font-weight: 600;")
        layout.addWidget(mapping_heading)
        mapping_explanation = QLabel(
            "Map each included reactant atom to the same-element product atom. "
            "Unmapped rows are saved as a draft; pack-step remains blocked until "
            "both endpoints have a complete one-to-one source mapping.",
            self,
        )
        mapping_explanation.setWordWrap(True)
        layout.addWidget(mapping_explanation)

        mapping_actions = QHBoxLayout()
        self.mapping_status = QLabel(self)
        self.mapping_status.setWordWrap(True)
        self.mapping_status.setAccessibleName("Atom correspondence readiness")
        mapping_actions.addWidget(self.mapping_status, 1)
        self.suggest_mapping_button = QPushButton("Suggest by structure", self)
        self.suggest_mapping_button.setToolTip(
            "Fill unmapped atoms from the maximum common substructure (RDKit). "
            "Suggestions are a starting point — review them before saving."
        )
        self.suggest_mapping_button.clicked.connect(self._suggest_structural_mapping)
        self.suggest_mapping_button.setEnabled(
            self._correspondence_suggester is not None
        )
        mapping_actions.addWidget(self.suggest_mapping_button)
        self.identity_mapping_button = QPushButton("Map identical atom IDs", self)
        self.identity_mapping_button.setToolTip(
            "Suggest only exact Chemvas atom IDs shared by both endpoints."
        )
        self.identity_mapping_button.clicked.connect(self._map_identical_atom_ids)
        mapping_actions.addWidget(self.identity_mapping_button)
        self.clear_mapping_button = QPushButton("Clear active mappings", self)
        self.clear_mapping_button.clicked.connect(self._clear_active_mappings)
        mapping_actions.addWidget(self.clear_mapping_button)
        layout.addLayout(mapping_actions)

        self.suggestion_status = QLabel(self)
        self.suggestion_status.setWordWrap(True)
        self.suggestion_status.setAccessibleName("Structural suggestion status")
        layout.addWidget(self.suggestion_status)

        self.mapping_table = _NoInputMethodTableWidget(0, 3, self)
        # Same constraint as the components table above: no direct cell editing.
        self.mapping_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.mapping_table.setAccessibleName("Atom correspondence table")
        self.mapping_table.setHorizontalHeaderLabels(
            ("Reactant atom", "Product atom", "Status")
        )
        mapping_vertical_header = self.mapping_table.verticalHeader()
        if mapping_vertical_header is not None:
            mapping_vertical_header.setVisible(False)
        mapping_horizontal_header = self.mapping_table.horizontalHeader()
        if mapping_horizontal_header is not None:
            mapping_horizontal_header.setStretchLastSection(True)
        self.mapping_table.currentCellChanged.connect(self._mapping_row_changed)
        layout.addWidget(self.mapping_table)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save
            | QDialogButtonBox.StandardButton.Cancel,
            parent=self,
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self.step_selector.currentIndexChanged.connect(self._load_selected_step)
        self._load_new_step_defaults()

    def _endpoint_fields(
        self,
        label: str,
        parent_layout: QHBoxLayout,
    ) -> _EndpointWidgets:
        state_id = QLineEdit(self)
        charge = QSpinBox(self)
        charge.setRange(-100, 100)
        multiplicity = QSpinBox(self)
        multiplicity.setRange(1, 100)
        multiplicity.setValue(1)
        form = QFormLayout()
        form.addRow(f"{label} state", state_id)
        form.addRow("Charge", charge)
        form.addRow("Multiplicity", multiplicity)
        parent_layout.addLayout(form)
        return _EndpointWidgets(state_id, charge, multiplicity)

    def _populate_component_rows(self) -> None:
        for row, component in enumerate(self._components):
            formula = "".join(
                f"{label}{count if count != 1 else ''}"
                for label, count in component.formula_labels
            )
            component_item = QTableWidgetItem(f"{component.index}: {formula}")
            component_item.setFlags(
                component_item.flags() & ~Qt.ItemFlag.ItemIsEditable
            )
            atom_ids_item = QTableWidgetItem(
                ", ".join(str(atom_id) for atom_id in component.atom_ids)
            )
            atom_ids_item.setFlags(atom_ids_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.table.setItem(row, 0, component_item)
            self.table.setItem(row, 1, atom_ids_item)
            for side, inclusion_column, role_column in (
                ("reactant", 2, 3),
                ("product", 4, 5),
            ):
                inclusion = self._inclusion_combo(side)
                role = self._role_combo(side)
                inclusion.currentIndexChanged.connect(
                    lambda _index, active_side=side, active_row=row: (
                        self._inclusion_changed(active_side, active_row)
                    )
                )
                role.currentIndexChanged.connect(
                    lambda _index, active_side=side, active_row=row: self._role_changed(
                        active_side, active_row
                    )
                )
                self._inclusion_combos[(side, row)] = inclusion
                self._role_combos[(side, row)] = role
                self.table.setCellWidget(row, inclusion_column, inclusion)
                self.table.setCellWidget(row, role_column, role)
        self.table.resizeColumnsToContents()

    def _inclusion_combo(self, side: str) -> QComboBox:
        combo = QComboBox(self.table)
        combo.addItem("Unused", _UNUSED)
        combo.addItem("Included in geometry", "included")
        combo.addItem("Context only", "context_only")
        combo.setAccessibleName(f"{side} inclusion")
        return combo

    def _role_combo(self, side: str) -> QComboBox:
        combo = QComboBox(self.table)
        combo.addItem(side.capitalize(), side)
        combo.addItem("Catalyst", "catalyst")
        combo.addItem("Spectator", "spectator")
        combo.setAccessibleName(f"{side} role")
        combo.setEnabled(False)
        return combo

    def _inclusion_changed(self, side: str, row: int) -> None:
        inclusion = self._inclusion_value(side, row)
        role_combo = self._role_combos[(side, row)]
        role_combo.setEnabled(inclusion != _UNUSED)
        if inclusion == "context_only" and role_combo.currentData() == side:
            blocked = role_combo.blockSignals(True)
            role_combo.setCurrentIndex(role_combo.findData("spectator"))
            role_combo.blockSignals(blocked)
        if not self._loading:
            self._apply_side_selection_effects()

    def _role_changed(self, _side: str, _row: int) -> None:
        # A role change can flip a component between reactive and catalyst/
        # spectator, which changes whether the opposite endpoint is locked.
        if not self._loading:
            self._apply_side_selection_effects()

    def _apply_side_selection_effects(self) -> None:
        was_loading = self._loading
        self._loading = True
        try:
            self._refresh_cross_side_availability()
        finally:
            self._loading = was_loading
        self._sync_modeled_charge("reactant")
        self._sync_modeled_charge("product")
        self._refresh_mapping_table()

    def _reactive_role_active(self, side: str, row: int) -> bool:
        # "Reactive" means the component is the endpoint's actual reactant or
        # product (role equal to the side), as opposed to a catalyst or
        # spectator that legitimately appears on both endpoints.
        if self._inclusion_value(side, row) == _UNUSED:
            return False
        return str(self._role_combos[(side, row)].currentData()) == side

    def _refresh_cross_side_availability(self) -> None:
        # A component consumed as this endpoint's reactant (or produced as its
        # product) cannot also appear at the other endpoint, so lock the other
        # side. Catalysts and spectators are not reactive and stay editable on
        # both sides. Locking only disables — it never clears an existing
        # selection, so switching a role back unlocks the other side intact.
        for row in range(len(self._components)):
            reactant_reactive = self._reactive_role_active("reactant", row)
            product_reactive = self._reactive_role_active("product", row)
            self._set_side_locked(
                "product", row, locked=reactant_reactive and not product_reactive
            )
            self._set_side_locked(
                "reactant", row, locked=product_reactive and not reactant_reactive
            )

    def _set_side_locked(self, side: str, row: int, *, locked: bool) -> None:
        inclusion_combo = self._inclusion_combos[(side, row)]
        role_combo = self._role_combos[(side, row)]
        if locked:
            inclusion_combo.setEnabled(False)
            role_combo.setEnabled(False)
            consumed_as = "product" if side == "reactant" else "reactant"
            inclusion_combo.setToolTip(
                f"This component is the step's {consumed_as}; a consumed species "
                "is not present at the other endpoint. Use Catalyst or Spectator "
                "to keep it on both sides."
            )
        else:
            inclusion_combo.setEnabled(True)
            role_combo.setEnabled(inclusion_combo.currentData() != _UNUSED)
            inclusion_combo.setToolTip("")

    def _sync_modeled_charge(self, side: str) -> None:
        charge = sum(
            component.formal_charge
            for row, component in enumerate(self._components)
            if self._inclusion_value(side, row) == "included"
        )
        self._endpoint_widgets(side).charge.setValue(charge)

    def _endpoint_widgets(self, side: str) -> _EndpointWidgets:
        return self.reactant_widgets if side == "reactant" else self.product_widgets

    def _inclusion_value(self, side: str, row: int) -> str:
        return str(self._inclusion_combos[(side, row)].currentData())

    def _load_selected_step(self) -> None:
        step_id = self.step_selector.currentData()
        if step_id is None or self._plan is None:
            self._load_new_step_defaults()
            return
        step = next(step for step in self._plan.steps if step.id == step_id)
        reactant_state = calculation_state_by_id(self._plan, step.reactant.state_id)
        product_state = calculation_state_by_id(self._plan, step.product.state_id)
        self._loading = True
        try:
            self.step_id.setReadOnly(True)
            self.step_id.setText(step.id)
            self._load_endpoint("reactant", reactant_state, step.reactant)
            self._load_endpoint("product", product_state, step.product)
            self._mapping_by_reactant = {
                atom_id: None for atom_id in included_atom_ids(reactant_state)
            }
            self._mapping_by_reactant.update(
                {
                    entry.reactant_atom_id: entry.product_atom_id
                    for entry in step.atom_correspondence
                }
            )
        finally:
            self._loading = False
        self._apply_side_selection_effects()

    def _load_new_step_defaults(self) -> None:
        existing_step_ids = (
            {step.id for step in self._plan.steps} if self._plan else set()
        )
        number = 1
        while f"S{number:02d}" in existing_step_ids:
            number += 1
        self._loading = True
        try:
            self._mapping_by_reactant = {}
            self.step_id.setReadOnly(False)
            self.step_id.setText(f"S{number:02d}")
            self.reactant_widgets.state_id.setText(f"R{number:02d}")
            self.product_widgets.state_id.setText(f"P{number:02d}")
            for side in ("reactant", "product"):
                self._endpoint_widgets(side).multiplicity.setValue(1)
                for row in range(len(self._components)):
                    self._set_combo_data(self._inclusion_combos[(side, row)], _UNUSED)
                    self._set_combo_data(self._role_combos[(side, row)], side)
                    self._role_combos[(side, row)].setEnabled(False)
                self._sync_modeled_charge(side)
        finally:
            self._loading = False
        self._apply_side_selection_effects()

    def _load_endpoint(self, side: str, state: CalculationState, endpoint) -> None:
        widgets = self._endpoint_widgets(side)
        widgets.state_id.setText(state.id)
        widgets.charge.setValue(state.charge)
        widgets.multiplicity.setValue(state.multiplicity)
        member_by_ids = {member.component_atom_ids: member for member in state.members}
        role_by_ids = {role.component_atom_ids: role.role for role in endpoint.roles}
        for row, component in enumerate(self._components):
            member = member_by_ids.get(component.atom_ids)
            inclusion = member.inclusion if member is not None else _UNUSED
            self._set_combo_data(self._inclusion_combos[(side, row)], inclusion)
            self._set_combo_data(
                self._role_combos[(side, row)],
                role_by_ids.get(component.atom_ids, side),
            )
            self._role_combos[(side, row)].setEnabled(member is not None)

    @staticmethod
    def _set_combo_data(combo: QComboBox, value: str) -> None:
        index = combo.findData(value)
        if index >= 0:
            combo.setCurrentIndex(index)

    def _build_endpoint(
        self, side: str
    ) -> tuple[CalculationState, CalculationStepEndpoint]:
        widgets = self._endpoint_widgets(side)
        members: list[CalculationStateMember] = []
        roles: list[CalculationEndpointRole] = []
        for row, component in enumerate(self._components):
            inclusion = self._inclusion_value(side, row)
            if inclusion == _UNUSED:
                continue
            members.append(CalculationStateMember(component.atom_ids, inclusion))
            roles.append(
                CalculationEndpointRole(
                    component.atom_ids,
                    str(self._role_combos[(side, row)].currentData()),
                )
            )
        state_id = widgets.state_id.text().strip()
        state = CalculationState(
            id=state_id,
            charge=widgets.charge.value(),
            multiplicity=widgets.multiplicity.value(),
            members=tuple(members),
        )
        return state, CalculationStepEndpoint(state_id, tuple(roles))

    def _refresh_mapping_table(self) -> None:
        self._clear_mapping_highlight()
        reactant_state, _reactant_endpoint = self._build_endpoint("reactant")
        product_state, _product_endpoint = self._build_endpoint("product")
        reactant_ids = included_atom_ids(reactant_state)
        product_ids = included_atom_ids(product_state)
        self._seed_new_identity_defaults(
            reactant_state=reactant_state,
            product_state=product_state,
        )

        was_loading = self._loading
        self._loading = True
        try:
            self.mapping_table.setRowCount(len(reactant_ids))
            self._mapping_combos = {}
            self._mapping_row_by_reactant = {}
            for row, reactant_atom_id in enumerate(sorted(reactant_ids)):
                self._mapping_row_by_reactant[reactant_atom_id] = row
                reactant_item = QTableWidgetItem(
                    self._atom_description(reactant_atom_id)
                )
                reactant_item.setFlags(
                    reactant_item.flags() & ~Qt.ItemFlag.ItemIsEditable
                )
                reactant_item.setData(Qt.ItemDataRole.UserRole, reactant_atom_id)
                self.mapping_table.setItem(row, 0, reactant_item)

                product_combo = _MappingProductCombo(self.mapping_table)
                product_combo.setAccessibleName(
                    "Product atom for reactant "
                    f"{self._atom_elements[reactant_atom_id]} "
                    f"#{reactant_atom_id}"
                )
                product_combo.addItem("Unmapped", None)
                current_product = self._mapping_by_reactant.get(reactant_atom_id)
                matching_product_ids = [
                    product_atom_id
                    for product_atom_id in sorted(product_ids)
                    if self._atom_elements[product_atom_id]
                    == self._atom_elements[reactant_atom_id]
                ]
                for product_atom_id in matching_product_ids:
                    product_combo.addItem(
                        self._atom_description(product_atom_id), product_atom_id
                    )
                if (
                    type(current_product) is int
                    and current_product in product_ids
                    and current_product not in matching_product_ids
                ):
                    product_combo.addItem(
                        self._atom_description(current_product) + " — invalid element",
                        current_product,
                    )
                if type(current_product) is int:
                    current_index = product_combo.findData(current_product)
                    if current_index >= 0:
                        product_combo.setCurrentIndex(current_index)
                product_combo.currentIndexChanged.connect(
                    lambda _index, atom_id=reactant_atom_id, combo=product_combo: (
                        self._mapping_changed(atom_id, combo)
                    )
                )
                product_combo.highlighted.connect(
                    lambda index, atom_id=reactant_atom_id, combo=product_combo: (
                        self._mapping_candidate_highlighted(atom_id, combo, index)
                    )
                )
                product_combo.popup_closed.connect(
                    lambda atom_id=reactant_atom_id, combo=product_combo: (
                        self._show_mapping_highlight(atom_id, combo.currentData())
                    )
                )
                self._mapping_combos[reactant_atom_id] = product_combo
                self.mapping_table.setCellWidget(row, 1, product_combo)

                status_item = QTableWidgetItem()
                status_item.setFlags(status_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                self.mapping_table.setItem(row, 2, status_item)
        finally:
            self._loading = was_loading
        self.mapping_table.resizeColumnsToContents()
        self._update_mapping_status()

    def _seed_new_identity_defaults(
        self,
        *,
        reactant_state: CalculationState,
        product_state: CalculationState,
    ) -> None:
        active_reactant_ids = included_atom_ids(reactant_state)
        used_product_ids = {
            product_atom_id
            for reactant_atom_id, product_atom_id in self._mapping_by_reactant.items()
            if reactant_atom_id in active_reactant_ids and type(product_atom_id) is int
        }
        for entry in identity_correspondence(reactant_state, product_state):
            atom_id = entry.reactant_atom_id
            if atom_id in self._mapping_by_reactant:
                continue
            if entry.product_atom_id not in used_product_ids:
                self._mapping_by_reactant[atom_id] = entry.product_atom_id
                used_product_ids.add(entry.product_atom_id)
            else:
                self._mapping_by_reactant[atom_id] = None

    def _map_identical_atom_ids(self) -> None:
        reactant_state, _reactant_endpoint = self._build_endpoint("reactant")
        product_state, _product_endpoint = self._build_endpoint("product")
        active_reactant_ids = included_atom_ids(reactant_state)
        used_product_ids = {
            product_atom_id
            for reactant_atom_id, product_atom_id in self._mapping_by_reactant.items()
            if reactant_atom_id in active_reactant_ids and type(product_atom_id) is int
        }
        for entry in identity_correspondence(reactant_state, product_state):
            if self._mapping_by_reactant.get(entry.reactant_atom_id) is not None:
                continue
            if entry.product_atom_id in used_product_ids:
                continue
            self._mapping_by_reactant[entry.reactant_atom_id] = entry.product_atom_id
            used_product_ids.add(entry.product_atom_id)
        self._refresh_mapping_table()

    def _clear_active_mappings(self) -> None:
        reactant_state, _reactant_endpoint = self._build_endpoint("reactant")
        for atom_id in included_atom_ids(reactant_state):
            self._mapping_by_reactant[atom_id] = None
        self._refresh_mapping_table()

    def _suggest_structural_mapping(self) -> None:
        if self._correspondence_suggester is None:
            return
        reactant_state, _reactant_endpoint = self._build_endpoint("reactant")
        product_state, _product_endpoint = self._build_endpoint("product")
        reactant_ids = included_atom_ids(reactant_state)
        product_ids = included_atom_ids(product_state)
        suggestions = self._correspondence_suggester(
            frozenset(reactant_ids), frozenset(product_ids)
        )
        used_product_ids = {
            product_atom_id
            for reactant_atom_id, product_atom_id in self._mapping_by_reactant.items()
            if reactant_atom_id in reactant_ids and type(product_atom_id) is int
        }
        applied = 0
        for reactant_atom_id, product_atom_id in suggestions:
            # Only fill gaps: never overwrite a mapping the researcher already
            # set, keep the same-element rule, and never reuse a product atom.
            if (
                reactant_atom_id not in reactant_ids
                or product_atom_id not in product_ids
            ):
                continue
            if self._mapping_by_reactant.get(reactant_atom_id) is not None:
                continue
            if product_atom_id in used_product_ids:
                continue
            if (
                self._atom_elements[reactant_atom_id]
                != self._atom_elements[product_atom_id]
            ):
                continue
            self._mapping_by_reactant[reactant_atom_id] = product_atom_id
            used_product_ids.add(product_atom_id)
            applied += 1
        self._refresh_mapping_table()
        if applied:
            note = (
                f"Suggested {applied} mapping(s) from the shared substructure. "
                "Review them and map the reaction center yourself."
            )
        else:
            note = (
                "No new structural suggestion — RDKit found no shared substructure "
                "beyond what is already mapped."
            )
        self.suggestion_status.setText(note)

    def _mapping_changed(self, reactant_atom_id: int, combo: QComboBox) -> None:
        if self._loading:
            return
        product_atom_id = combo.currentData()
        self._mapping_by_reactant[reactant_atom_id] = (
            product_atom_id if type(product_atom_id) is int else None
        )
        self._update_mapping_status()
        self._show_mapping_highlight(reactant_atom_id, product_atom_id)

    def _mapping_row_changed(
        self,
        current_row: int,
        _current_column: int,
        _previous_row: int,
        _previous_column: int,
    ) -> None:
        if self._loading or current_row < 0:
            return
        item = self.mapping_table.item(current_row, 0)
        if item is None:
            self._clear_mapping_highlight()
            return
        reactant_atom_id = item.data(Qt.ItemDataRole.UserRole)
        if type(reactant_atom_id) is not int:
            self._clear_mapping_highlight()
            return
        self._show_mapping_highlight(
            reactant_atom_id,
            self._mapping_by_reactant.get(reactant_atom_id),
        )

    def _mapping_candidate_highlighted(
        self,
        reactant_atom_id: int,
        combo: QComboBox,
        index: int,
    ) -> None:
        self._show_mapping_highlight(reactant_atom_id, combo.itemData(index))

    def _show_mapping_highlight(
        self,
        reactant_atom_id: int,
        product_atom_id: object,
    ) -> None:
        if self._mapping_highlighter is None:
            return
        self._mapping_highlighter.show_mapping(
            reactant_atom_id,
            product_atom_id if type(product_atom_id) is int else None,
        )

    def _clear_mapping_highlight(self) -> None:
        if self._mapping_highlighter is not None:
            self._mapping_highlighter.clear()

    def _active_correspondence(
        self,
        reactant_state: CalculationState,
        product_state: CalculationState,
    ) -> tuple[CalculationAtomCorrespondence, ...]:
        reactant_ids = included_atom_ids(reactant_state)
        product_ids = included_atom_ids(product_state)
        return tuple(
            CalculationAtomCorrespondence(reactant_atom_id, product_atom_id)
            for reactant_atom_id in sorted(reactant_ids)
            if type(product_atom_id := self._mapping_by_reactant.get(reactant_atom_id))
            is int
            and product_atom_id in product_ids
        )

    def _update_mapping_status(self) -> None:
        reactant_state, _reactant_endpoint = self._build_endpoint("reactant")
        product_state, _product_endpoint = self._build_endpoint("product")
        product_ids = included_atom_ids(product_state)
        correspondence = self._active_correspondence(
            reactant_state,
            product_state,
        )
        product_counts: dict[int, int] = {}
        mismatched_reactant_ids: set[int] = set()
        for entry in correspondence:
            product_counts[entry.product_atom_id] = (
                product_counts.get(entry.product_atom_id, 0) + 1
            )
            if (
                self._atom_elements[entry.reactant_atom_id]
                != self._atom_elements[entry.product_atom_id]
            ):
                mismatched_reactant_ids.add(entry.reactant_atom_id)
        duplicate_product_ids = {
            product_atom_id
            for product_atom_id, count in product_counts.items()
            if count > 1
        }
        readiness = correspondence_readiness(
            reactant_state,
            product_state,
            correspondence,
        )
        mapped_product_count = len(product_counts)
        prefix = (
            f"Mapped {readiness.mapped_atom_count}/"
            f"{readiness.reactant_atom_count} reactant atoms and "
            f"{mapped_product_count}/{readiness.product_atom_count} product atoms."
        )
        if mismatched_reactant_ids:
            message = prefix + " Invalid: mapped atom elements must match."
        elif duplicate_product_ids:
            duplicate_text = ", ".join(
                f"#{atom_id}" for atom_id in sorted(duplicate_product_ids)
            )
            message = prefix + f" Invalid: product atom {duplicate_text} is repeated."
        elif readiness.ready_for_step_pack:
            message = prefix + " Source atom mapping is ready for pack-step."
        else:
            message = prefix + " Draft mapping; pack-step remains blocked."
        self.mapping_status.setText(message)

        for reactant_atom_id, row in self._mapping_row_by_reactant.items():
            product_atom_id = self._mapping_by_reactant.get(reactant_atom_id)
            if product_atom_id is None or product_atom_id not in product_ids:
                status = "Unmapped"
            elif reactant_atom_id in mismatched_reactant_ids:
                status = "Element mismatch"
            elif product_atom_id in duplicate_product_ids:
                status = "Duplicate product"
            else:
                status = "Mapped"
            item = self.mapping_table.item(row, 2)
            if item is not None:
                item.setText(status)

    def _atom_description(self, atom_id: int) -> str:
        return (
            f"{self._atom_elements[atom_id]} #{atom_id} · component "
            f"{self._component_index_by_atom[atom_id]}"
        )

    def accept(self) -> None:
        try:
            reactant_state, reactant_endpoint = self._build_endpoint("reactant")
            product_state, product_endpoint = self._build_endpoint("product")
            step_id = self.step_id.text().strip()
            selected_step_id = self.step_selector.currentData()
            if (
                selected_step_id is None
                and self._plan is not None
                and any(step.id == step_id for step in self._plan.steps)
            ):
                raise ValueError(
                    f"Step {step_id} already exists. Select Edit {step_id} instead."
                )
            correspondence = self._active_correspondence(
                reactant_state,
                product_state,
            )
            plan = plan_with_replaced_step(
                self._document_state,
                current_plan_state=(
                    calculation_plan_to_state(self._plan)
                    if self._plan is not None
                    else None
                ),
                reactant_state=reactant_state,
                product_state=product_state,
                step=CalculationStep(
                    id=step_id,
                    reactant=reactant_endpoint,
                    product=product_endpoint,
                    atom_correspondence=correspondence,
                ),
            )
        except ValueError as exc:
            QMessageBox.warning(self, "Invalid calculation step", str(exc))
            return
        self.result_plan_state = calculation_plan_to_state(plan)
        super().accept()

    def done(self, result: int) -> None:
        self._clear_mapping_highlight()
        super().done(result)


def _correspondence_suggester_for(
    canvas: Any, document_state: Mapping[str, object]
) -> _CorrespondenceSuggester | None:
    adapter = getattr(canvas, "rdkit", None)
    raw_model = document_state.get("model")
    if adapter is None or not isinstance(raw_model, Mapping):
        return None
    model = deserialize_model_state(cast(Mapping[str, object], raw_model))

    def suggest(
        reactant_atom_ids: frozenset[int],
        product_atom_ids: frozenset[int],
    ) -> list[tuple[int, int]]:
        return adapter.suggest_atom_correspondence(
            model, reactant_atom_ids, product_atom_ids
        )

    return suggest


def edit_calculation_plan_for_window(
    window: Any,
    *,
    dialog_factory: Callable[..., CalculationStepDialog] = CalculationStepDialog,
) -> bool:
    canvas = active_canvas_for_window(window)
    document_state = document_session_service_for_window(window).snapshot_state()
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
        mapping_highlighter.clear()
    if dialog_result != QDialog.DialogCode.Accepted:
        return False
    if dialog.result_plan_state is None:
        raise RuntimeError("Accepted calculation dialog did not return a plan.")
    set_calculation_plan_for(canvas, dialog.result_plan_state)
    services = services_for_window(window)
    services.canvas_document_service.refresh_tab_title(window, canvas)
    services.status_service.refresh_status_context(window)
    return True


__all__ = ["CalculationStepDialog", "edit_calculation_plan_for_window"]
