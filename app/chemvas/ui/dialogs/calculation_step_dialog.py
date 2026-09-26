from __future__ import annotations

import copy
from collections import Counter
from pathlib import Path
from typing import TYPE_CHECKING, override

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QBrush, QColor
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QBoxLayout,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from chemvas.core.calculation_handoff_folder import publish_handoff_folder
from chemvas.domain.document import (
    CalculationAtomCorrespondence,
    CalculationEndpointRole,
    CalculationState,
    CalculationStateMember,
    CalculationStep,
    CalculationStepEndpoint,
    MoleculeModel,
    calculation_plan_to_state,
)
from chemvas.features.calculation_bundle import (
    apply_calculation_step_edit,
    calculation_state_by_id,
    correspondence_readiness,
    fill_correspondence_gaps,
    identity_correspondence,
    included_atom_ids,
    prepare_calculation_step_editor,
)
from chemvas.shell.palette import PALETTE
from chemvas.ui.dialogs.calculation_handoff_check import CalculationHandoffCheck
from chemvas.ui.dialogs.calculation_step_widgets import (
    CanvasMappingSnapshot,
    _CorrespondenceSuggester,
    _EndpointWidgets,
    _MappingHighlighter,
    _MappingProductCombo,
    _NoInputMethodTableWidget,
)

if TYPE_CHECKING:
    from collections.abc import Callable

_UNUSED = "unused"

# Painted onto a combo whose endpoint is locked by the opposite side's reactive
# role, so the lock is visible at a glance and not just a disabled control.
_LOCKED_COMBO_STYLE = (
    f"QComboBox {{"
    f"  background: {PALETTE['surface_app']};"
    f"  color: {PALETTE['text_faint']};"
    f"  border: 1px solid {PALETTE['border']};"
    f"}}"
)


class CalculationStepDialog(QDialog):
    plan_saved = pyqtSignal(object)
    mapping_updated = pyqtSignal()
    focus_atom_requested = pyqtSignal(int)

    def __init__(
        self,
        document_state: dict[str, object],
        *,
        parent: QWidget | None = None,
        embedded: bool = False,
        snapshot_is_current: Callable[[], bool] | None = None,
        mapping_highlighter: _MappingHighlighter | None = None,
        correspondence_suggester: _CorrespondenceSuggester | None = None,
    ) -> None:
        # Validate before allocating a parent-owned widget. A failed constructor
        # must not leave an invisible, partially initialized editor in the dock.
        inventory, plan = prepare_calculation_step_editor(document_state)
        super().__init__(parent)
        self._embedded = embedded
        self._snapshot_is_current = snapshot_is_current
        self._selected_reactant: int | None = None
        self._changed_bonds: list[tuple[int, int]] = []
        if embedded:
            self.setWindowFlags(Qt.WindowType.Widget)
        self.setWindowTitle("Reaction Mapping")
        self.resize(1080, 760)
        self._document_state = document_state
        self._mapping_highlighter = mapping_highlighter
        self._correspondence_suggester = correspondence_suggester
        self._plan = plan
        self._components = inventory.components
        model = inventory.model
        self._model = model
        self._atom_elements = {
            atom_id: atom.element for atom_id, atom in model.atoms.items()
        }
        self._component_index_by_atom = {
            atom_id: component.index
            for component in self._components
            for atom_id in component.atom_ids
        }
        self.result_plan_state: dict[str, object] | None = None
        self._loading = False
        self._inclusion_combos: dict[tuple[str, int], QComboBox] = {}
        self._role_combos: dict[tuple[str, int], QComboBox] = {}
        self._mapping_by_reactant: dict[int, int | None] = {}
        self._mapping_combos: dict[int, QComboBox] = {}
        self._mapping_row_by_reactant: dict[int, int] = {}

        outer = QVBoxLayout(self)
        self.tabs = QTabWidget(self)
        outer.addWidget(self.tabs)
        structures = QWidget(self)
        mapping = QWidget(self)
        export = QWidget(self)
        self.tabs.addTab(structures, "Structures")
        self.tabs.addTab(mapping, "Mapping")
        self.tabs.addTab(export, "Geometry export")
        layout = QVBoxLayout(structures)
        explanation = QLabel(
            "Choose reactant and product structures, then connect their atoms on the Mapping tab. "
            "Save mapping to document records the correspondence; File → Save writes the .chemvas file."
        )
        explanation.setWordWrap(True)
        layout.addWidget(explanation)

        self.step_selector = QComboBox(self)
        self.step_selector.addItem("New pair", None)
        if self._plan is not None:
            for step in self._plan.steps:
                self.step_selector.addItem(f"Saved pair {step.id}", step.id)
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
                "Reactant",
                "Reactant role",
                "Product",
                "Product role",
            )
        )
        vertical_header = self.table.verticalHeader()
        if vertical_header is not None:
            vertical_header.setVisible(False)
        horizontal_header = self.table.horizontalHeader()
        if horizontal_header is not None:
            horizontal_header.setStretchLastSection(False)
            horizontal_header.setSectionResizeMode(
                QHeaderView.ResizeMode.ResizeToContents
            )
            for column in (2, 4):
                horizontal_header.setSectionResizeMode(
                    column, QHeaderView.ResizeMode.Stretch
                )
        self._populate_component_rows()
        layout.addWidget(self.table)

        self.advanced = QCheckBox("Show IDs and component roles", self)
        layout.addWidget(self.advanced)
        self.advanced.toggled.connect(self._show_advanced)
        self._build_mapping_page(mapping, model)

        self._build_export_page(export)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save
            | QDialogButtonBox.StandardButton.Cancel,
            parent=self,
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        if embedded:
            cancel_button = buttons.button(QDialogButtonBox.StandardButton.Cancel)
            if cancel_button is not None:
                cancel_button.hide()
        outer.addWidget(buttons)
        save_button = buttons.button(QDialogButtonBox.StandardButton.Save)
        if save_button is not None:
            save_button.setText("Save mapping to document")

        self.step_selector.currentIndexChanged.connect(self._load_selected_step)
        self._load_new_step_defaults()
        for field in (
            self.step_id,
            self.reactant_widgets.state_id,
            self.product_widgets.state_id,
        ):
            field.textChanged.connect(self._invalidate_check)
        for endpoint in (self.reactant_widgets, self.product_widgets):
            endpoint.charge.valueChanged.connect(self._invalidate_check)
            endpoint.multiplicity.valueChanged.connect(self._invalidate_check)
        self._show_advanced(False)

    def _build_mapping_page(self, mapping: QWidget, model: MoleculeModel) -> None:
        layout = QVBoxLayout(mapping)
        self.mapping_mode = QCheckBox("Map atoms on canvas", self)
        layout.addWidget(self.mapping_mode)
        next_unmapped = QPushButton("Next unmapped atom", self)
        next_unmapped.clicked.connect(self._next_unmapped)
        layout.addWidget(next_unmapped)
        mapping_heading = QLabel("Atom correspondence", self)
        mapping_heading.setStyleSheet("font-weight: 600;")
        layout.addWidget(mapping_heading)
        mapping_explanation = QLabel(
            "Map each included reactant atom to the same-element product atom. "
            "Point to a label, carbon corner or bond endpoint to see its matched pair. "
            "Click a reactant, then its product. Save partial mappings at any time. "
            "Orange bonds show changes between the drawn structures, not a reaction mechanism.",
            self,
        )
        mapping_explanation.setWordWrap(True)
        layout.addWidget(mapping_explanation)

        mapping_actions = QVBoxLayout() if self._embedded else QHBoxLayout()
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
            mapping_horizontal_header.setSectionResizeMode(
                0, QHeaderView.ResizeMode.ResizeToContents
            )
            mapping_horizontal_header.setSectionResizeMode(
                1, QHeaderView.ResizeMode.ResizeToContents
            )
            mapping_horizontal_header.setSectionResizeMode(
                2, QHeaderView.ResizeMode.Stretch
            )
        if self._embedded:
            table_toggle = QCheckBox("Show mapping table", self)
            table_toggle.toggled.connect(self.mapping_table.setVisible)
            layout.addWidget(table_toggle)
            self.mapping_table.hide()
        layout.addWidget(self.mapping_table)

    def _show_advanced(self, visible: bool) -> None:
        for column in (1, 3, 5):
            self.table.setColumnHidden(column, not visible)
        for field in (
            self.step_id,
            self.reactant_widgets.state_id,
            self.product_widgets.state_id,
        ):
            field.setVisible(visible)
            parent_layout = field.parentWidget()
            if parent_layout is not None:
                for label in self.findChildren(QLabel):
                    if label.text() in ("Step ID", "Reactant state", "Product state"):
                        label.setVisible(visible)

    def _build_export_page(self, page: QWidget) -> None:
        layout = QVBoxLayout(page)
        explanation = QLabel(
            "Optional geometry handoff. Saving a 2D reaction mapping does not require this check. "
            "The check expands hydrogens and "
            "abbreviations, validates atom identities and charge/multiplicity consistency, "
            "and generates initial component geometries. It does not arrange components, "
            "optimize quantum endpoints or run NEB.",
            self,
        )
        explanation.setWordWrap(True)
        layout.addWidget(explanation)
        self.check_button = QPushButton("Check expanded atoms and geometry", self)
        self.check_button.clicked.connect(self._start_check)
        layout.addWidget(self.check_button)
        self.cancel_check_button = QPushButton("Cancel check", self)
        self.cancel_check_button.clicked.connect(self.cancel_geometry_check)
        self.cancel_check_button.setEnabled(False)
        layout.addWidget(self.cancel_check_button)
        self.check_status = QLabel(
            "Not checked. Complete the source mapping first.", self
        )
        self.check_status.setWordWrap(True)
        self.check_status.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        layout.addWidget(self.check_status)
        self.review_checkbox = QCheckBox(
            "Mapping, charge and multiplicity reviewed",
            self,
        )
        self.review_checkbox.setEnabled(False)
        self.review_checkbox.toggled.connect(self._review_changed)
        layout.addWidget(self.review_checkbox)
        self.export_button = QPushButton("Export new handoff folder…", self)
        self.export_button.setEnabled(False)
        self.export_button.clicked.connect(self._export_pair)
        layout.addWidget(self.export_button)
        layout.addStretch()
        self._checked_artifact: dict[str, object] | None = None
        self._checked_source = b""
        self._checker = CalculationHandoffCheck(self)
        self._checker.finished.connect(self._check_finished)
        self._checking = False

    @property
    def has_structures(self) -> bool:
        return bool(self._components)

    def invalidate_source(self) -> None:
        """Disable this draft and its checked output after the source changes."""
        self.mapping_mode.setChecked(False)
        self._invalidate_check()
        self.setEnabled(False)

    def cancel_geometry_check(self) -> None:
        self._checker.cancel()

    def _invalidate_check(self) -> None:
        self._checked_artifact = None
        self._checked_source = b""
        self.review_checkbox.setChecked(False)
        self.review_checkbox.setEnabled(False)
        self.export_button.setEnabled(False)
        self.check_status.setText(
            "Not checked. Run the expanded-atom check for this pair."
        )
        if self._checking:
            self._checker.cancel()

    def _review_changed(self, checked: bool) -> None:
        self.export_button.setEnabled(checked and self._checked_artifact is not None)

    def _start_check(self) -> None:
        self._invalidate_check()
        self.mapping_mode.setChecked(False)
        try:
            self._ensure_current_snapshot()
            state = copy.deepcopy(self._document_state)
            state["calculation_plan"] = self._draft_plan_state()
            # FailedToStart can finish synchronously inside QProcess.start.
            self._checking = True
            self.check_button.setEnabled(False)
            self.cancel_check_button.setEnabled(True)
            for index in (0, 1):
                self.tabs.setTabEnabled(index, False)
            self.check_status.setText(
                "Checking expanded atoms and generating initial geometry…"
            )
            self._checker.start(state, self.step_id.text().strip())
        except (OSError, ValueError) as exc:
            self._check_finished(None, b"", str(exc))

    def _check_finished(self, artifact: object, source: bytes, error: str) -> None:
        self._checking = False
        self.check_button.setEnabled(True)
        self.cancel_check_button.setEnabled(False)
        for index in (0, 1):
            self.tabs.setTabEnabled(index, True)
        if error or not isinstance(artifact, dict):
            self.check_status.setText(error or "No check result was produced.")
            return
        if artifact["handoff"]["status"] != "ready":
            self.check_status.setText(
                "Endpoint check blocked: " + ", ".join(artifact["handoff"]["codes"])
            )
            return
        self._checked_artifact = artifact
        self._checked_source = source
        data = artifact["payload"]["data"]
        geometry = data["endpoint_geometry"]
        outcomes = []
        for side, side_geometry in geometry["sides"].items():
            for component in side_geometry["components"]:
                outcomes.append(
                    f"{side} component {component['component_index']}: {component['geometry_generation']['optimization_result']}"
                )
        self.check_status.setText(
            "Expanded atom mapping and electronic-state consistency passed.\n"
            + "\n".join(outcomes)
            + "\nResearcher review required. Multiple components have no relative placement."
        )
        self.review_checkbox.setEnabled(True)

    def _export_pair(self) -> None:
        if self._checked_artifact is None or not self.review_checkbox.isChecked():
            return
        name, _ = QFileDialog.getSaveFileName(
            self, "Choose a NEW handoff folder", "reaction-pair"
        )
        if not name:
            return
        try:
            self._ensure_current_snapshot()
            publish_handoff_folder(
                Path(name), self._checked_artifact, self._checked_source
            )
        except (OSError, ValueError) as exc:
            QMessageBox.warning(self, "Could not export pair", str(exc))
            return
        self.check_status.setText(
            f"Exported to {name}. The folder includes the checked source snapshot, machine.json and XYZ files. External endpoint preparation remains required."
        )

    def canvas_mapping_snapshot(self) -> CanvasMappingSnapshot:
        reactant, _ = self._build_endpoint("reactant")
        product, _ = self._build_endpoint("product")
        return CanvasMappingSnapshot(
            atoms=tuple(
                (key, atom.x, atom.y) for key, atom in self._model.atoms.items()
            ),
            pairs=tuple(
                (entry.reactant_atom_id, entry.product_atom_id)
                for entry in self._active_correspondence(reactant, product)
            ),
            reactant_ids=frozenset(included_atom_ids(reactant)),
            product_ids=frozenset(included_atom_ids(product)),
            changed_bonds=tuple(self._changed_bonds),
            selected_reactant=self._selected_reactant,
        )

    def clear_canvas_mapping_selection(self) -> None:
        self._selected_reactant = None
        self.mapping_updated.emit()

    def pick_canvas_atom(self, atom_id: int) -> bool:
        """Advance the editor-owned selection; report a completed pair."""
        if self._selected_reactant is not None:
            self._pick_product(atom_id)
            return self._selected_reactant is None
        elif atom_id in self._mapping_combos:
            self._pick_reactant(atom_id)
            self.suggestion_status.setText(
                self.suggestion_status.text()
                + " Click its product atom to set the mapping."
            )
        else:
            self.suggestion_status.setText("Choose an included reactant atom first.")
        return False

    def _pick_reactant(self, atom_id: int) -> None:
        self._selected_reactant = atom_id
        self.mapping_updated.emit()
        row = self._mapping_row_by_reactant.get(atom_id)
        if row is not None:
            self.mapping_table.selectRow(row)
            item = self.mapping_table.item(row, 0)
            if item is not None:
                self.mapping_table.scrollToItem(item)

    def _pick_product(self, atom_id: int) -> None:
        selected = self._selected_reactant
        combo = self._mapping_combos.get(selected) if selected is not None else None
        if combo is None:
            self.suggestion_status.setText("Select a reactant atom on the left first.")
            return
        index = combo.findData(atom_id)
        if index < 0:
            self.suggestion_status.setText(
                "Choose a product atom with the same element."
            )
            return
        if any(
            product == atom_id and reactant != selected
            for reactant, product in self._mapping_by_reactant.items()
            if reactant in self._mapping_combos
        ):
            self.suggestion_status.setText(
                "That product atom is already mapped. Clear its existing mapping first."
            )
            return
        combo.setCurrentIndex(index)
        self._selected_reactant = None
        self.mapping_updated.emit()
        self.suggestion_status.setText("Pair updated. Click the next reactant atom.")

    def _next_unmapped(self) -> None:
        ids = sorted(
            atom_id
            for atom_id in self._mapping_combos
            if self._mapping_by_reactant.get(atom_id) is None
        )
        if ids:
            selected = self._selected_reactant
            self._pick_reactant(
                next(
                    (
                        atom_id
                        for atom_id in ids
                        if selected is None or atom_id > selected
                    ),
                    ids[0],
                )
            )

        if self._selected_reactant is not None:
            self.focus_atom_requested.emit(self._selected_reactant)

    def _refresh_mapping_changes(
        self, reactant: CalculationState, product: CalculationState
    ) -> None:
        correspondence = self._active_correspondence(reactant, product)
        pairs = {
            entry.reactant_atom_id: entry.product_atom_id for entry in correspondence
        }
        model = self._model
        rbonds: dict[tuple[int, ...], int] = {
            (min(bond.a, bond.b), max(bond.a, bond.b)): bond.order
            for bond in model.bonds
            if bond is not None and bond.a in pairs and bond.b in pairs
        }
        inverse = {value: key for key, value in pairs.items()}
        pbonds: dict[tuple[int, ...], int] = {
            (min(bond.a, bond.b), max(bond.a, bond.b)): bond.order
            for bond in model.bonds
            if bond is not None and bond.a in inverse and bond.b in inverse
        }
        rchanged = [
            (key[0], key[1])
            for key, order in rbonds.items()
            if pbonds.get(tuple(sorted((pairs[key[0]], pairs[key[1]])))) != order
        ]
        pchanged = [
            (key[0], key[1])
            for key, order in pbonds.items()
            if rbonds.get(tuple(sorted((inverse[key[0]], inverse[key[1]])))) != order
        ]
        self._changed_bonds = rchanged + pchanged
        self.mapping_updated.emit()

    def _ensure_current_snapshot(self) -> None:
        if self._snapshot_is_current is not None and not self._snapshot_is_current():
            self._invalidate_check()
            raise ValueError(
                "The drawing changed. Reload the Reaction Mapping panel before continuing."
            )

    def _endpoint_fields(
        self,
        label: str,
        parent_layout: QBoxLayout,
    ) -> _EndpointWidgets:
        state_id = QLineEdit(self)
        charge = QSpinBox(self)
        charge.setRange(-100, 100)
        multiplicity = QSpinBox(self)
        multiplicity.setRange(1, 100)
        multiplicity.setValue(1)
        form = QFormLayout()
        form.addRow(QLabel(label, self))
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
        combo.addItem("Include", "included")
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

    def _side_locked(self, side: str, row: int) -> bool:
        # Context is not consumed and may legitimately describe the species on
        # the opposite side of a CLI-authored plan.
        if self._inclusion_value(side, row) == "context_only":
            return False
        opposite_side = "product" if side == "reactant" else "reactant"
        return self._reactive_role_active(
            opposite_side, row
        ) and not self._reactive_role_active(side, row)

    def _refresh_cross_side_availability(self) -> None:
        # A component consumed as this endpoint's reactant (or produced as its
        # product) cannot also appear at the other endpoint, so lock the other
        # side. Catalysts and spectators are not reactive and stay editable on
        # both sides. Locking only disables — it never clears an existing
        # selection, so switching a role back unlocks the other side intact.
        for row in range(len(self._components)):
            self._set_side_locked(
                "product",
                row,
                locked=self._side_locked("product", row),
            )
            self._set_side_locked(
                "reactant",
                row,
                locked=self._side_locked("reactant", row),
            )

    def _set_side_locked(self, side: str, row: int, *, locked: bool) -> None:
        inclusion_combo = self._inclusion_combos[(side, row)]
        role_combo = self._role_combos[(side, row)]
        if locked:
            inclusion_combo.setEnabled(False)
            role_combo.setEnabled(False)
            consumed_as = "product" if side == "reactant" else "reactant"
            lock_reason = (
                f"This component is the step's {consumed_as}; a consumed species "
                "is not present at the other endpoint. Use Catalyst or Spectator "
                "to keep it on both sides."
            )
            inclusion_combo.setToolTip(lock_reason)
            role_combo.setToolTip(lock_reason)
            inclusion_combo.setStyleSheet(_LOCKED_COMBO_STYLE)
            role_combo.setStyleSheet(_LOCKED_COMBO_STYLE)
        else:
            inclusion_combo.setEnabled(True)
            role_combo.setEnabled(inclusion_combo.currentData() != _UNUSED)
            inclusion_combo.setToolTip("")
            role_combo.setToolTip("")
            inclusion_combo.setStyleSheet("")
            role_combo.setStyleSheet("")

    def _sync_modeled_charge(self, side: str) -> None:
        charge = sum(
            component.formal_charge
            for row, component in enumerate(self._components)
            if self._inclusion_value(side, row) == "included"
            and not self._side_locked(side, row)
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
            if self._side_locked(side, row):
                continue
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
                # An atom with no same-element product candidate cannot be mapped
                # until the counterpart component joins the product endpoint, so
                # its row reads muted rather than actionable.
                if not any(
                    self._atom_elements[product_atom_id]
                    == self._atom_elements[reactant_atom_id]
                    for product_atom_id in product_ids
                ):
                    reactant_item.setForeground(QBrush(QColor(PALETTE["text_faint"])))
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
                self._mapping_combos[reactant_atom_id] = product_combo
                self.mapping_table.setCellWidget(row, 1, product_combo)

                status_item = QTableWidgetItem()
                status_item.setFlags(status_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                self.mapping_table.setItem(row, 2, status_item)
        finally:
            self._loading = was_loading
        self._update_mapping_status()

    def _seed_new_identity_defaults(
        self,
        *,
        reactant_state: CalculationState,
        product_state: CalculationState,
    ) -> None:
        active_reactant_ids = included_atom_ids(reactant_state)
        active_product_ids = included_atom_ids(product_state)
        candidates = tuple(
            (entry.reactant_atom_id, entry.product_atom_id)
            for entry in identity_correspondence(reactant_state, product_state)
        )
        replaceable_reactant_ids = {
            reactant_atom_id
            for reactant_atom_id, _product_atom_id in candidates
            if reactant_atom_id not in self._mapping_by_reactant
        }
        seeded = dict(self._mapping_by_reactant)
        for reactant_atom_id in replaceable_reactant_ids:
            seeded[reactant_atom_id] = None
        self._mapping_by_reactant, _applied = fill_correspondence_gaps(
            seeded,
            candidates,
            active_reactant_ids=active_reactant_ids,
            active_product_ids=active_product_ids,
            replaceable_reactant_ids=replaceable_reactant_ids,
        )

    def _map_identical_atom_ids(self) -> None:
        reactant_state, _reactant_endpoint = self._build_endpoint("reactant")
        product_state, _product_endpoint = self._build_endpoint("product")
        active_reactant_ids = included_atom_ids(reactant_state)
        active_product_ids = included_atom_ids(product_state)
        replaceable_reactant_ids = {
            atom_id
            for atom_id in active_reactant_ids
            if self._mapping_by_reactant.get(atom_id) is None
        }
        self._mapping_by_reactant, _applied = fill_correspondence_gaps(
            self._mapping_by_reactant,
            (
                (entry.reactant_atom_id, entry.product_atom_id)
                for entry in identity_correspondence(reactant_state, product_state)
            ),
            active_reactant_ids=active_reactant_ids,
            active_product_ids=active_product_ids,
            replaceable_reactant_ids=replaceable_reactant_ids,
        )
        self._refresh_mapping_table()

    def _clear_active_mappings(self) -> None:
        reactant_state, _reactant_endpoint = self._build_endpoint("reactant")
        for atom_id in included_atom_ids(reactant_state):
            self._mapping_by_reactant[atom_id] = None
            combo = self._mapping_combos[atom_id]
            blocked = combo.blockSignals(True)
            combo.setCurrentIndex(0)
            combo.blockSignals(blocked)
        self._update_mapping_status()

    def _suggest_structural_mapping(self) -> None:
        if self._correspondence_suggester is None:
            return
        reactant_state, _reactant_endpoint = self._build_endpoint("reactant")
        product_state, _product_endpoint = self._build_endpoint("product")
        reactant_ids = included_atom_ids(reactant_state)
        product_ids = included_atom_ids(product_state)
        existing_correspondence = {
            reactant_atom_id: product_atom_id
            for reactant_atom_id in sorted(reactant_ids)
            if type(product_atom_id := self._mapping_by_reactant.get(reactant_atom_id))
            is int
            and product_atom_id in product_ids
        }
        result = self._correspondence_suggester(
            frozenset(reactant_ids),
            frozenset(product_ids),
            existing_correspondence,
        )
        if result.value is None:
            # A failed suggestion is not "no shared substructure": presenting
            # a tool problem as a chemistry result sends the researcher
            # hunting for a drawing error that does not exist.
            self.suggestion_status.setText(
                result.error or "The structural suggestion failed."
            )
            return
        suggestions = result.value
        replaceable_reactant_ids = {
            atom_id
            for atom_id in reactant_ids
            if self._mapping_by_reactant.get(atom_id) is None
        }
        self._mapping_by_reactant, applied = fill_correspondence_gaps(
            self._mapping_by_reactant,
            suggestions,
            active_reactant_ids=reactant_ids,
            active_product_ids=product_ids,
            replaceable_reactant_ids=replaceable_reactant_ids,
            atom_elements=self._atom_elements,
        )
        self._refresh_mapping_table()
        if applied:
            note = (
                f"Suggested {applied} mapping(s) from the shared substructure. "
                "Review them and map the reaction center yourself."
            )
        else:
            note = (
                "No new structural suggestion — this connected-substructure "
                "heuristic found no additional pairs. Existing mappings are kept; "
                "review the remaining atoms manually."
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
        self._invalidate_check()
        reactant_state, _reactant_endpoint = self._build_endpoint("reactant")
        product_state, _product_endpoint = self._build_endpoint("product")
        product_ids = included_atom_ids(product_state)
        correspondence = self._active_correspondence(
            reactant_state,
            product_state,
        )
        if self._mapping_highlighter is not None:
            # Label colors track the mapping itself: a mapped reactant/product
            # atom takes its endpoint tint, every other atom stays gray until
            # it is mapped.
            mapped_reactant_ids = {entry.reactant_atom_id for entry in correspondence}
            mapped_product_ids = {entry.product_atom_id for entry in correspondence}
            all_atom_ids = {
                atom_id
                for component in self._components
                for atom_id in component.atom_ids
            }
            self._mapping_highlighter.show_atom_labels(
                mapped_reactant_ids,
                mapped_product_ids,
                all_atom_ids - mapped_reactant_ids - mapped_product_ids,
            )
        self._refresh_mapping_changes(reactant_state, product_state)
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
            message = prefix + " Source mapping complete. Save it to the document."
        else:
            message = prefix + " Draft mapping; you can save it and continue later."
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
        self._refresh_used_candidate_marks()

    def _refresh_used_candidate_marks(self) -> None:
        # A product atom already mapped by another row would only produce a
        # "Duplicate product" error if picked again, so it shows muted in every
        # other row's dropdown. Marking only — the pick stays possible and the
        # existing duplicate validation still decides.
        muted = QBrush(QColor(PALETTE["text_faint"]))
        used_counts = Counter(self._mapping_by_reactant.values())
        for reactant_atom_id, combo in self._mapping_combos.items():
            for index in range(1, combo.count()):
                product_atom_id = combo.itemData(index)
                if type(product_atom_id) is not int:
                    continue
                used_by_other = used_counts[product_atom_id] > (
                    self._mapping_by_reactant.get(reactant_atom_id) == product_atom_id
                )
                combo.setItemData(
                    index,
                    muted if used_by_other else None,
                    Qt.ItemDataRole.ForegroundRole,
                )

    def _atom_description(self, atom_id: int) -> str:
        return (
            f"{self._atom_elements[atom_id]} #{atom_id} · component "
            f"{self._component_index_by_atom[atom_id]}"
        )

    def _draft_plan_state(self) -> dict[str, object]:
        reactant_state, reactant_endpoint = self._build_endpoint("reactant")
        product_state, product_endpoint = self._build_endpoint("product")
        step_id = self.step_id.text().strip()
        selected_step_id = self.step_selector.currentData()
        correspondence = self._active_correspondence(
            reactant_state,
            product_state,
        )
        step = CalculationStep(
            id=step_id,
            reactant=reactant_endpoint,
            product=product_endpoint,
            atom_correspondence=correspondence,
        )
        plan = apply_calculation_step_edit(
            self._document_state,
            current_plan=self._plan,
            selected_step_id=selected_step_id,
            reactant_state=reactant_state,
            product_state=product_state,
            step=step,
        )
        return calculation_plan_to_state(plan)

    @override
    def accept(self) -> None:
        try:
            self._ensure_current_snapshot()
            self.result_plan_state = self._draft_plan_state()
        except ValueError as exc:
            QMessageBox.warning(self, "Invalid reaction pair", str(exc))
            return
        if self._embedded:
            self.plan_saved.emit(self.result_plan_state)
        else:
            super().accept()

    @override
    def reject(self) -> None:
        if self._embedded:
            self.mapping_mode.setChecked(False)
            return
        super().reject()

    @override
    def done(self, result: int) -> None:
        self.shutdown()
        super().done(result)

    def shutdown(self) -> None:
        self.mapping_mode.setChecked(False)
        self._checker.shutdown()
        if self._mapping_highlighter is not None:
            self._mapping_highlighter.clear_all()


__all__ = [
    "CalculationStepDialog",
]
