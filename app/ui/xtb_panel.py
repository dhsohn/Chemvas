from __future__ import annotations

from collections.abc import Callable, Sequence

from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QApplication,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from core.xtb_adapter import XTBAdapter


class XTBPanel(QWidget):
    def __init__(self, xtb_adapter: XTBAdapter | None = None) -> None:
        super().__init__()
        self._canvas = None
        self._canvas_sheet_name = ""
        self._open_result_canvas_callback: Callable[..., tuple[str | None, object | None]] | None = None
        self._xtb = xtb_adapter or XTBAdapter()
        self._input_payload: dict | None = None
        self._output_payload: dict | None = None
        self._result_sheet_counter = 0

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        self.control_frame = QFrame(self)
        self.control_frame.setObjectName("xtbControlFrame")
        control_layout = QVBoxLayout(self.control_frame)
        control_layout.setContentsMargins(12, 12, 12, 12)
        control_layout.setSpacing(10)

        title = QLabel("GFN2-xTB / CREST")
        title.setStyleSheet("font-weight: 700;")
        control_layout.addWidget(title)

        self.availability_label = QLabel()
        self.availability_label.setWordWrap(True)
        control_layout.addWidget(self.availability_label)

        self.current_selection_label = QLabel("Current selection: none")
        self.current_selection_label.setWordWrap(True)
        control_layout.addWidget(self.current_selection_label)

        self.input_label = QLabel("Reactant/Input: not set")
        self.input_label.setWordWrap(True)
        control_layout.addWidget(self.input_label)

        self.output_label = QLabel("Product/Output: not set")
        self.output_label.setWordWrap(True)
        control_layout.addWidget(self.output_label)

        capture_row = QHBoxLayout()
        self.capture_input_button = QPushButton("Set Reactant")
        self.capture_input_button.clicked.connect(self.capture_input_from_selection)
        capture_row.addWidget(self.capture_input_button)
        self.capture_output_button = QPushButton("Set Product")
        self.capture_output_button.clicked.connect(self.capture_output_from_selection)
        capture_row.addWidget(self.capture_output_button)
        self.clear_button = QPushButton("Clear Capture")
        self.clear_button.clicked.connect(self.clear_captured_structures)
        capture_row.addWidget(self.clear_button)
        control_layout.addLayout(capture_row)

        action_grid = QGridLayout()
        action_grid.setHorizontalSpacing(8)
        action_grid.setVerticalSpacing(8)

        self.optimize_button = QPushButton("Input Optimization")
        self.optimize_button.clicked.connect(self.optimize_input_structure)
        action_grid.addWidget(self.optimize_button, 0, 0)

        self.crest_button = QPushButton("CREST")
        self.crest_button.clicked.connect(self.run_crest_search)
        action_grid.addWidget(self.crest_button, 0, 1)

        self.compare_button = QPushButton("Pair Single-Point")
        self.compare_button.clicked.connect(self.compare_structures)
        action_grid.addWidget(self.compare_button, 1, 0)

        self.path_button = QPushButton("Reaction Path")
        self.path_button.clicked.connect(self.run_reaction_path_analysis)
        action_grid.addWidget(self.path_button, 1, 1)

        control_layout.addLayout(action_grid)

        hint = QLabel(
            "Capture reactant/product selections from any canvas sheet. "
            "Each workflow opens a canvas result sheet."
        )
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #6f6457;")
        control_layout.addWidget(hint)

        layout.addWidget(self.control_frame, 0)

        self.status_frame = QFrame(self)
        self.status_frame.setObjectName("xtbStatusFrame")
        status_layout = QVBoxLayout(self.status_frame)
        status_layout.setContentsMargins(12, 12, 12, 12)
        status_layout.setSpacing(8)

        result_title = QLabel("Result Delivery")
        result_title.setStyleSheet("font-weight: 700;")
        status_layout.addWidget(result_title)

        self.result_mode_label = QLabel("All xTB results are opened as canvas tabs.")
        self.result_mode_label.setWordWrap(True)
        status_layout.addWidget(self.result_mode_label)

        self.last_result_label = QLabel("Last result: none")
        self.last_result_label.setWordWrap(True)
        status_layout.addWidget(self.last_result_label)
        status_layout.addStretch(1)

        layout.addWidget(self.status_frame, 1)

        self.setStyleSheet(
            """
            QFrame#xtbControlFrame, QFrame#xtbStatusFrame {
                background: #f8f2ea;
                border: 1px solid #d9ccbc;
                border-radius: 12px;
            }
            QPushButton {
                border: 1px solid #d4c9bb;
                border-radius: 6px;
                padding: 6px 10px;
                background: #fbf8f3;
            }
            QPushButton:hover {
                background: #efe6da;
                border-color: #c4b6a4;
            }
            QPushButton:disabled {
                color: #998d81;
                background: #f0ebe4;
            }
            """
        )

        self.refresh_availability()
        self.refresh_current_selection()

    def set_canvas(self, canvas, *, sheet_name: str = "") -> None:
        self._canvas = canvas
        self._canvas_sheet_name = sheet_name
        self.refresh_current_selection()

    def set_result_canvas_callback(self, callback) -> None:
        self._open_result_canvas_callback = callback

    def refresh_availability(self) -> None:
        xtb_available = self._xtb.is_available()
        crest_available = self._xtb.is_crest_available()
        xtb_message = self._xtb.availability_message()
        crest_message = self._xtb.crest_availability_message()
        self.availability_label.setText(f"{xtb_message}\n{crest_message}")
        self.optimize_button.setEnabled(xtb_available)
        self.compare_button.setEnabled(xtb_available)
        self.path_button.setEnabled(xtb_available)
        self.crest_button.setEnabled(crest_available)

    def refresh_current_selection(self) -> None:
        if self._canvas is None:
            self.current_selection_label.setText("Current selection: no active canvas sheet")
            return
        try:
            payload = self._capture_payload_from_canvas()
        except Exception:
            self.current_selection_label.setText(
                f"Current selection ({self._canvas_sheet_name or 'Active Sheet'}): none"
            )
            return
        self.current_selection_label.setText(f"Current selection: {payload['summary']}")

    def clear_captured_structures(self) -> None:
        self._input_payload = None
        self._output_payload = None
        self.input_label.setText("Reactant/Input: not set")
        self.output_label.setText("Product/Output: not set")
        self.refresh_current_selection()

    def clear_results(self) -> None:
        self._set_last_result("Result sheets are delivered as canvas tabs.")

    def snapshot_state(self) -> dict:
        return {}

    def restore_state(self, state: dict | None) -> None:
        self._result_sheet_counter = 0
        if state:
            self._restore_legacy_result_sheets(state)

    def capture_input_from_selection(self) -> None:
        try:
            self._input_payload = self._capture_payload_from_canvas()
        except Exception as exc:
            self._open_message_canvas("Capture", str(exc))
            return
        self.input_label.setText(f"Reactant/Input: {self._input_payload['summary']}")

    def capture_output_from_selection(self) -> None:
        try:
            self._output_payload = self._capture_payload_from_canvas()
        except Exception as exc:
            self._open_message_canvas("Capture", str(exc))
            return
        self.output_label.setText(f"Product/Output: {self._output_payload['summary']}")

    def optimize_input_structure(self) -> None:
        if self._input_payload is None:
            self._open_message_canvas("Optimization", "Set a reactant/input structure first.")
            return
        if not self._xtb.is_available():
            self.refresh_availability()
            self._open_message_canvas("Optimization", self._xtb.availability_message())
            return
        result = self._run_with_wait_cursor(
            lambda: self._xtb.optimize(
                self._input_payload["model"],
                atom_annotations=self._input_payload["atom_annotations"],
                bond_length_px=self._canvas.renderer.style.bond_length_px if self._canvas is not None else 40.0,
            )
        )
        if result is None or result.canvas_model is None:
            self._open_message_canvas("Optimization", self._xtb.last_error or "GFN2-xTB optimization failed.")
            return

        sheet_name, canvas = self._open_result_canvas(self._next_result_canvas_title("Opt"))
        if canvas is None:
            self._set_last_result("Optimization finished, but no result canvas callback is configured.")
            return
        self._configure_result_canvas(canvas)
        center = self._canvas_center(canvas)
        bond = canvas.renderer.style.bond_length_px
        canvas.insert_structure_model(
            result.canvas_model,
            center=QPointF(center.x() - bond * 2.5, center.y() + bond * 0.6),
            title=self._result_note_banner("GFN2-xTB Optimization", result.total_energy_hartree, result.homo_lumo_gap_ev),
        )
        note_text = self._compose_note(
            "Optimization Summary",
            self._workflow_lines("opt", result.command, self._input_payload),
            [
                ("TOTAL ENERGY", self._format_float(result.total_energy_hartree, "Eh")),
                ("HOMO-LUMO GAP", self._format_float(result.homo_lumo_gap_ev, "eV")),
                ("GRADIENT NORM", self._format_gradient(result.gradient_norm)),
                ("Input", self._payload_text(self._input_payload)),
                ("Output", f"{sheet_name or 'Optimized Output'}: {self._model_summary(result.canvas_model, {})}"),
                ("Output Excerpt", self._excerpt_text(self._run_text_block(result))),
            ],
        )
        self._add_note(canvas, QPointF(center.x() + bond * 2.7, center.y() - bond * 3.2), note_text)

        self._output_payload = self._build_payload(
            result.canvas_model,
            {},
            result.canvas_model.bounds(),
            sheet_name=sheet_name or "Optimized Output",
        )
        self.output_label.setText(f"Product/Output: {self._output_payload['summary']}")
        self._set_last_result(f"Optimization result opened in canvas tab {sheet_name or 'Optimized Output'}.")

    def run_crest_search(self) -> None:
        if self._input_payload is None:
            self._open_message_canvas("CREST", "Set a reactant/input structure first.")
            return
        if not self._xtb.is_crest_available():
            self.refresh_availability()
            self._open_message_canvas("CREST", self._xtb.crest_availability_message())
            return
        result = self._run_with_wait_cursor(
            lambda: self._xtb.crest_search(
                self._input_payload["model"],
                atom_annotations=self._input_payload["atom_annotations"],
                bond_length_px=self._canvas.renderer.style.bond_length_px if self._canvas is not None else 40.0,
            )
        )
        if result is None:
            self._open_message_canvas("CREST", self._xtb.last_error or "CREST conformer search failed.")
            return

        sheet_name, canvas = self._open_result_canvas(self._next_result_canvas_title("CREST"))
        if canvas is None:
            self._set_last_result("CREST finished, but no result canvas callback is configured.")
            return
        self._configure_result_canvas(canvas)
        center = self._canvas_center(canvas)
        bond = canvas.renderer.style.bond_length_px
        if result.canvas_model is not None:
            canvas.insert_structure_model(
                result.canvas_model,
                center=QPointF(center.x() - bond * 2.5, center.y() + bond * 0.6),
                title=self._result_note_banner("CREST Best Conformer", result.total_energy_hartree, result.homo_lumo_gap_ev),
            )
        note_text = self._compose_note(
            "CREST Summary",
            self._workflow_lines("crest", result.command, self._input_payload),
            [
                ("Conformer Count", str(result.conformer_count or 0)),
                ("TOTAL ENERGY", self._format_float(result.total_energy_hartree, "Eh")),
                ("HOMO-LUMO GAP", self._format_float(result.homo_lumo_gap_ev, "eV")),
                ("GRADIENT NORM", self._format_gradient(result.gradient_norm)),
                ("Input", self._payload_text(self._input_payload)),
                ("Output", sheet_name or "CREST Result"),
                ("Output Excerpt", self._excerpt_text(self._crest_text_block(result))),
            ],
        )
        self._add_note(canvas, QPointF(center.x() + bond * 2.7, center.y() - bond * 3.2), note_text)

        if result.canvas_model is not None:
            self._output_payload = self._build_payload(
                result.canvas_model,
                {},
                result.canvas_model.bounds(),
                sheet_name=sheet_name or "CREST Result",
            )
            self.output_label.setText(f"Product/Output: {self._output_payload['summary']}")
        self._set_last_result(f"CREST result opened in canvas tab {sheet_name or 'CREST Result'}.")

    def compare_structures(self) -> None:
        if self._input_payload is None or self._output_payload is None:
            self._open_message_canvas("Single-Point", "Set both reactant/input and product/output structures first.")
            return
        if not self._xtb.is_available():
            self.refresh_availability()
            self._open_message_canvas("Single-Point", self._xtb.availability_message())
            return
        result = self._run_with_wait_cursor(
            lambda: self._xtb.compare_pair_singlepoint(
                self._input_payload["model"],
                self._output_payload["model"],
                input_annotations=self._input_payload["atom_annotations"],
                output_annotations=self._output_payload["atom_annotations"],
            )
        )
        if result is None:
            self._open_message_canvas("Single-Point", self._xtb.last_error or "Pair single-point analysis failed.")
            return

        sheet_name, canvas = self._open_result_canvas(self._next_result_canvas_title("Pair SP"))
        if canvas is None:
            self._set_last_result("Pair single-point finished, but no result canvas callback is configured.")
            return
        self._configure_result_canvas(canvas)
        center = self._canvas_center(canvas)
        bond = canvas.renderer.style.bond_length_px
        canvas.insert_structure_model(
            self._input_payload["model"],
            center=QPointF(center.x() - bond * 5.5, center.y() + bond * 1.1),
            title="Reactant",
        )
        canvas.insert_structure_model(
            self._output_payload["model"],
            center=QPointF(center.x() + bond * 5.5, center.y() + bond * 1.1),
            title="Product",
        )
        note_text = self._compose_note(
            "Pair Single-Point",
            self._workflow_lines("sp", result.input_result.command, self._input_payload, self._output_payload),
            [
                ("Delta E (output - input)", self._format_float(result.delta_energy_kcal_mol, "kcal/mol")),
                ("Input TOTAL ENERGY", self._format_float(result.input_result.total_energy_hartree, "Eh")),
                ("Output TOTAL ENERGY", self._format_float(result.output_result.total_energy_hartree, "Eh")),
                ("Input GAP", self._format_float(result.input_result.homo_lumo_gap_ev, "eV")),
                ("Output GAP", self._format_float(result.output_result.homo_lumo_gap_ev, "eV")),
                ("Output Excerpt", self._excerpt_text(self._comparison_text_block(result))),
            ],
        )
        self._add_note(canvas, QPointF(center.x() - bond * 4.0, center.y() - bond * 5.7), note_text)
        self._set_last_result(f"Pair single-point result opened in canvas tab {sheet_name or 'Pair SP'}.")

    def run_reaction_path_analysis(self) -> None:
        if self._input_payload is None or self._output_payload is None:
            self._open_message_canvas("Reaction Path", "Set both reactant/input and product/output structures first.")
            return
        if not self._xtb.is_available():
            self.refresh_availability()
            self._open_message_canvas("Reaction Path", self._xtb.availability_message())
            return
        result = self._run_with_wait_cursor(
            lambda: self._xtb.reaction_path(
                self._input_payload["model"],
                self._output_payload["model"],
                input_annotations=self._input_payload["atom_annotations"],
                output_annotations=self._output_payload["atom_annotations"],
            )
        )
        if result is None:
            self._open_message_canvas("Reaction Path", self._xtb.last_error or "Reaction path analysis failed.")
            return

        sheet_name, canvas = self._open_result_canvas(self._next_result_canvas_title("Path"))
        if canvas is None:
            self._set_last_result("Reaction path finished, but no result canvas callback is configured.")
            return
        self._configure_result_canvas(canvas)
        center = self._canvas_center(canvas)
        bond = canvas.renderer.style.bond_length_px
        canvas.insert_structure_model(
            self._input_payload["model"],
            center=QPointF(center.x() - bond * 7.0, center.y() + bond * 1.4),
            title="Reactant",
        )
        canvas.insert_structure_model(
            self._output_payload["model"],
            center=QPointF(center.x() + bond * 7.0, center.y() + bond * 1.4),
            title="Product",
        )
        ts_model = self._transition_state_model(result.transition_state_xyz)
        if ts_model is not None:
            canvas.insert_structure_model(
                ts_model,
                center=QPointF(center.x(), center.y() + bond * 1.4),
                title="TS Guess",
            )
        note_text = self._compose_note(
            "Reaction Path Analysis",
            self._workflow_lines("path", result.command, self._input_payload, self._output_payload),
            [
                ("Forward Barrier", self._format_float(result.forward_barrier_kcal_mol, "kcal/mol")),
                ("Backward Barrier", self._format_float(result.backward_barrier_kcal_mol, "kcal/mol")),
                ("Reaction Energy", self._format_float(result.reaction_energy_kcal_mol, "kcal/mol")),
                ("TS Guess", "inserted on this sheet" if ts_model is not None else "not available"),
                ("Output Excerpt", self._excerpt_text(self._reaction_path_text_block(result))),
            ],
        )
        self._add_note(canvas, QPointF(center.x() - bond * 5.0, center.y() - bond * 6.2), note_text)
        self._set_last_result(f"Reaction path result opened in canvas tab {sheet_name or 'Path'}.")

    def _capture_payload_from_canvas(self) -> dict:
        if self._canvas is None:
            raise ValueError("There is no active canvas sheet.")
        model, atom_annotations, bounds = self._canvas.build_selected_structure_payload()
        return self._build_payload(
            model,
            atom_annotations,
            bounds,
            sheet_name=self._canvas_sheet_name or "Active Sheet",
        )

    def _build_payload(self, model, atom_annotations, bounds, *, sheet_name: str) -> dict:
        summary = f"{sheet_name}: {self._model_summary(model, atom_annotations)}"
        return {
            "sheet_name": sheet_name,
            "model": model,
            "atom_annotations": atom_annotations,
            "bounds": bounds,
            "summary": summary,
        }

    @staticmethod
    def _model_summary(model, atom_annotations) -> str:
        atom_count = len(model.atoms)
        bond_count = sum(1 for bond in model.bonds if bond is not None)
        total_charge = sum(int(values.get("formal_charge", 0)) for values in atom_annotations.values())
        total_unpaired = sum(int(values.get("radical_electrons", 0)) for values in atom_annotations.values())
        return f"{atom_count} atoms, {bond_count} bonds, charge {total_charge:+d}, radicals {total_unpaired}"

    def _open_result_canvas(
        self,
        name: str,
        *,
        select: bool = True,
        exact_name: bool = False,
    ) -> tuple[str | None, object | None]:
        if self._open_result_canvas_callback is None:
            return None, None
        return self._open_result_canvas_callback(name, select=select, exact_name=exact_name)

    def _configure_result_canvas(self, canvas) -> None:
        canvas.apply_text_preset_paper_bold()
        canvas.text_font_family = "Arial"
        canvas.text_font_size = max(canvas.text_font_size, 11)
        canvas.text_line_spacing = 1.05
        canvas.text_alignment = Qt.AlignmentFlag.AlignLeft
        canvas.text_color = QColor("#1f1a17")
        canvas.note_box_enabled = True
        canvas.note_box_color = QColor("#fffdf8")
        canvas.note_box_alpha = 0.96
        canvas.note_border_enabled = True
        canvas.note_border_color = QColor("#c8b8a5")
        canvas.note_border_width = 1.0
        canvas.note_padding = 10.0

    @staticmethod
    def _canvas_center(canvas) -> QPointF:
        return canvas.mapToScene(canvas.viewport().rect().center())

    def _add_note(self, canvas, pos: QPointF, text: str) -> None:
        if not text.strip():
            return
        canvas.add_text_note(pos, text)

    def _transition_state_model(self, transition_state_xyz: str | None):
        if transition_state_xyz is None or self._input_payload is None or self._canvas is None:
            return None
        try:
            template_scene = self._xtb._build_scene(
                self._input_payload["model"],
                atom_annotations=self._input_payload["atom_annotations"],
                workflow_name="GFN2-xTB reaction path analysis",
            )
            if template_scene is None:
                return None
            ts_scene = self._xtb._scene_from_xyz(transition_state_xyz, template=template_scene)
            if ts_scene is None:
                return None
            return self._xtb._scene_to_canvas_model(
                ts_scene,
                bond_length_px=self._canvas.renderer.style.bond_length_px,
            )
        except Exception:
            return None

    def _open_message_canvas(self, title: str, message: str, *, select: bool = True) -> None:
        sheet_name, canvas = self._open_result_canvas(self._next_result_canvas_title(title), select=select)
        if canvas is None:
            self._set_last_result(message)
            return
        self._configure_result_canvas(canvas)
        center = self._canvas_center(canvas)
        bond = canvas.renderer.style.bond_length_px
        detail_lines = [
            ("Active Sheet", self._canvas_sheet_name or "n/a"),
            ("Reactant/Input", self._payload_text(self._input_payload)),
            ("Product/Output", self._payload_text(self._output_payload)),
            ("Message", message),
        ]
        note_text = self._compose_note(title, (), detail_lines)
        self._add_note(canvas, QPointF(center.x() - bond * 4.8, center.y() - bond * 4.2), note_text)
        self._set_last_result(f"{title} message opened in canvas tab {sheet_name or title}.")

    def _restore_legacy_result_sheets(self, state: dict) -> None:
        sheets = state.get("sheets", [])
        if not isinstance(sheets, list):
            return
        for sheet_state in sheets:
            if not isinstance(sheet_state, dict):
                continue
            title = str(sheet_state.get("title", "Legacy Result"))
            content = sheet_state.get("content", {})
            note_text = self._legacy_note_text(title, content if isinstance(content, dict) else {})
            sheet_name, canvas = self._open_result_canvas(title, select=False, exact_name=True)
            if canvas is None:
                continue
            self._configure_result_canvas(canvas)
            center = self._canvas_center(canvas)
            bond = canvas.renderer.style.bond_length_px
            self._add_note(canvas, QPointF(center.x() - bond * 4.8, center.y() - bond * 4.2), note_text)
            self._set_last_result(f"Legacy result restored in canvas tab {sheet_name or title}.")

    @staticmethod
    def _payload_text(payload: dict | None) -> str:
        if payload is None:
            return "not set"
        return payload["summary"]

    def _next_result_canvas_title(self, prefix: str) -> str:
        self._result_sheet_counter += 1
        return prefix

    def _run_with_wait_cursor(self, fn):
        QApplication.processEvents()
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            return fn()
        finally:
            QApplication.restoreOverrideCursor()

    def _set_last_result(self, text: str) -> None:
        self.last_result_label.setText(f"Last result: {text}")

    @staticmethod
    def _format_float(value: float | None, unit: str) -> str:
        if value is None:
            return "n/a"
        return f"{value:.4f} {unit}"

    @staticmethod
    def _format_gradient(value: float | None) -> str:
        if value is None:
            return "n/a"
        return f"{value:.6f}"

    @staticmethod
    def _result_note_banner(title: str, energy: float | None, gap: float | None) -> str:
        lines = [title]
        if energy is not None:
            lines.append(f"E = {energy:.6f} Eh")
        if gap is not None:
            lines.append(f"Gap = {gap:.3f} eV")
        return "\n".join(lines)

    def _workflow_lines(self, workflow: str, command: Sequence[str] | tuple[str, ...] | None, *payloads: dict | None) -> list[str]:
        lines = [f"Workflow: {workflow.upper()}"]
        if command:
            lines.append(f"Command: {' '.join(command)}")
        for label, payload in zip(("Reactant", "Product"), payloads):
            if payload is None:
                continue
            lines.append(f"{label} Sheet: {payload.get('sheet_name', 'n/a')}")
        return lines

    @staticmethod
    def _compose_note(title: str, intro_lines: Sequence[str], detail_pairs: Sequence[tuple[str, str]]) -> str:
        blocks = [title]
        if intro_lines:
            blocks.append("\n".join(line for line in intro_lines if line))
        details = [f"{label}: {value}" for label, value in detail_pairs if value]
        if details:
            blocks.append("\n".join(details))
        return "\n\n".join(block for block in blocks if block.strip())

    @staticmethod
    def _run_text_block(result) -> str:
        lines = []
        if getattr(result, "stdout", ""):
            lines.append(result.stdout.strip())
        if getattr(result, "stderr", ""):
            lines.append(result.stderr.strip())
        return "\n\n".join(line for line in lines if line)

    @staticmethod
    def _crest_text_block(result) -> str:
        lines = [XTBPanel._run_text_block(result)]
        if result.best_xyz:
            lines.append("Best conformer XYZ\n" + result.best_xyz.strip())
        return "\n\n".join(line for line in lines if line)

    @staticmethod
    def _comparison_text_block(result) -> str:
        lines = [
            "Input",
            XTBPanel._run_text_block(result.input_result),
            "",
            "Output",
            XTBPanel._run_text_block(result.output_result),
        ]
        return "\n".join(line for line in lines if line is not None).strip()

    @staticmethod
    def _reaction_path_text_block(result) -> str:
        lines = [XTBPanel._run_text_block(result)]
        if result.transition_state_xyz:
            lines.append("TS Guess XYZ\n" + result.transition_state_xyz.strip())
        return "\n\n".join(line for line in lines if line)

    @staticmethod
    def _excerpt_text(text: str, *, max_lines: int = 14, max_chars: int = 1800) -> str:
        normalized = text.strip()
        if not normalized:
            return ""
        lines = normalized.splitlines()
        if len(lines) > max_lines:
            lines = ["..."] + lines[-max_lines:]
        excerpt = "\n".join(lines)
        if len(excerpt) > max_chars:
            excerpt = "...\n" + excerpt[-max_chars:]
        return excerpt

    @staticmethod
    def _legacy_note_text(title: str, payload: dict) -> str:
        lines = [title]
        content_title = str(payload.get("title", "")).strip()
        if content_title and content_title != title:
            lines.extend(["", content_title])
        for key in ("subtitle", "summary_text", "reactant_text", "product_text", "cue_text", "notes_text"):
            value = str(payload.get(key, "")).strip()
            if value:
                lines.append("")
                lines.append(value)
        metadata = payload.get("metadata", [])
        if isinstance(metadata, list) and metadata:
            lines.append("")
            lines.append("Metadata")
            for item in metadata:
                if not isinstance(item, dict):
                    continue
                label = str(item.get("label", "")).strip()
                value = str(item.get("value", "")).strip()
                if label or value:
                    lines.append(f"{label}: {value}".strip(": "))
        highlights = payload.get("result_bullets", [])
        if isinstance(highlights, list) and highlights:
            lines.append("")
            lines.append("Result Highlights")
            for item in highlights:
                if not isinstance(item, dict):
                    continue
                label = str(item.get("label", "")).strip()
                value = str(item.get("value", "")).strip()
                if label or value:
                    lines.append(f"{label}: {value}".strip(": "))
        return "\n".join(lines).strip()
