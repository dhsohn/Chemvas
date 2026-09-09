from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QTextDocument
from PyQt6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from chemvas.core.history import CompositeCommand, HistoryCommand, MoveAtomsCommand
from chemvas.features.scheme_layout import MAX_LAYOUT_BLOCKS, validate_layout_request
from chemvas.ui.canvas_document_state import (
    document_item_lists_for,
    snapshot_canvas_document_state_with_warnings,
)
from chemvas.ui.canvas_service_ports import history_service_for_access
from chemvas.ui.history_commands import MoveItemsCommand, UpdateSceneItemCommand
from chemvas.ui.main_window_ports import active_canvas_for_window
from chemvas.ui.scene_item_state import arrow_state_dict_for
from chemvas.ui.scheme_layout_service import plan_canvas_layout
from chemvas.ui.selection_service_access import refresh_selection_outline_for
from chemvas.ui.transactions.document import document_transaction

if TYPE_CHECKING:
    from collections.abc import Callable

    from chemvas.features.scheme_layout import LayoutRequest
    from chemvas.ui.canvas_view import CanvasView


@dataclass(frozen=True)
class GroupLayoutChoice:
    group_index: int
    row: int
    order: int
    captions: tuple[int, ...]
    arrow_after: int | None = None
    column_group: str | None = None


def grouped_layout_request(
    source: dict[str, Any],
    choices: list[GroupLayoutChoice],
    *,
    gap: float = 40,
    row_gap: float = 30,
    caption_gap: float = 10,
    line_gap: float = 4,
    max_row_width: float | None = None,
    caption_alignment: str = "row",
    arrow_color: str | None = None,
) -> LayoutRequest:
    """Bind explicit existing groups to the same validated request as the CLI."""
    groups = source.get("groups", [])
    seen: set[int] = set()
    rows: dict[int, list[GroupLayoutChoice]] = {}
    for choice in choices:
        if choice.group_index in seen or not 0 <= choice.group_index < len(groups):
            raise ValueError("Each existing group may be listed once only.")
        seen.add(choice.group_index)
        if not 0 <= choice.row <= MAX_LAYOUT_BLOCKS or choice.order < 1:
            raise ValueError("Use row 0 to skip, or positive row and order numbers.")
        if choice.row:
            rows.setdefault(choice.row, []).append(choice)
    raw_rows = []
    for row_number, members in sorted(rows.items()):
        members.sort(key=lambda member: member.order)
        if len({member.order for member in members}) != len(members):
            raise ValueError(f"Row {row_number} has duplicate order numbers.")
        blocks = []
        for member in members:
            group = groups[member.group_index]
            references = [tuple(reference) for reference in group["items"]]
            if any(("notes", index) not in references for index in member.captions):
                raise ValueError("Caption numbers must name notes in their own group.")
            blocks.append(
                {
                    "atoms": group["atoms"],
                    "captions": list(member.captions),
                    "items": [
                        list(reference)
                        for reference in references
                        if reference not in {("notes", i) for i in member.captions}
                    ],
                }
            )
        if members[-1].arrow_after is not None:
            raise ValueError(
                f"The last group in row {row_number} cannot have an arrow after it."
            )
        arrows = [member.arrow_after for member in members[:-1]]
        if any(arrow is not None for arrow in arrows) and None in arrows:
            raise ValueError(
                f"Row {row_number}: choose every connecting arrow, or none."
            )
        raw_row: dict[str, object] = {"blocks": blocks}
        column_groups = {
            member.column_group for member in members if member.column_group is not None
        }
        if len(column_groups) > 1:
            raise ValueError(f"Row {row_number} has conflicting alignment groups.")
        if column_groups:
            raw_row["column_group"] = column_groups.pop()
        if any(arrow is not None for arrow in arrows):
            raw_row["arrows"] = arrows
        raw_rows.append(raw_row)
    digest = hashlib.sha256(json.dumps(source, sort_keys=True).encode()).hexdigest()
    raw: dict[str, object] = {
        "format": "chemvas-scheme-layout",
        "version": 1,
        "source_sha256": digest,
        "rows": raw_rows,
        "gap": gap,
        "row_gap": row_gap,
        "caption_gap": caption_gap,
        "line_gap": line_gap,
        "caption_alignment": caption_alignment,
    }
    if arrow_color is not None:
        raw["arrow_color"] = arrow_color
    if max_row_width is not None:
        raw["max_row_width"] = max_row_width
    return validate_layout_request(source, raw, source_sha256=digest)


def arrange_grouped_canvas(
    canvas: CanvasView, source: dict[str, Any], request: LayoutRequest
) -> dict[str, object]:
    """Apply measured translations as one undoable edit, keeping group identity."""
    current, warnings = snapshot_canvas_document_state_with_warnings(canvas)
    if warnings or current != source:
        raise ValueError("The drawing changed. Close and reopen Arrange Scheme.")
    plan = plan_canvas_layout(canvas, source, request)
    items = document_item_lists_for(canvas)
    commands: list[HistoryCommand] = []
    for index, color in plan.arrow_colors.items():
        item = items["arrows"][index]
        before = arrow_state_dict_for(canvas, item)
        after = {**before, "color": color}
        if before != after:
            commands.append(UpdateSceneItemCommand(item, before, after))
    commands.extend(
        MoveAtomsCommand(atom_ids=set(block.atoms), dx=dx, dy=dy)
        for block, dx, dy in plan.atom_moves
        if abs(dx) > 1e-9 or abs(dy) > 1e-9
    )
    commands.extend(
        MoveItemsCommand(items=[items[kind][index]], dx=dx, dy=dy)
        for (kind, index), (dx, dy) in plan.item_moves.items()
        if abs(dx) > 1e-9 or abs(dy) > 1e-9
    )
    if commands:
        history = history_service_for_access(canvas)
        with document_transaction(canvas, history_service=history):
            command = CompositeCommand(commands)
            command.redo(canvas)
            refresh_selection_outline_for(canvas)
            if not history.push(command):
                raise ValueError("History is disabled; the layout was not applied.")
    return plan.report


@dataclass(frozen=True)
class _GroupWidgets:
    index: int
    row: QSpinBox
    order: QSpinBox
    captions: QLineEdit
    arrow: QComboBox
    column_group: QLineEdit


def _note_title(note: dict[str, Any]) -> str:
    if not note.get("html"):
        return " ".join(str(note.get("text", "")).split())
    document = QTextDocument()
    document.setHtml(note.get("html", ""))
    return " ".join(document.toPlainText().split())


class SchemeLayoutDialog(QDialog):
    def __init__(
        self,
        source: dict[str, Any],
        *,
        arrange: Callable[[LayoutRequest], dict[str, object]],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        groups = source.get("groups", [])
        if not groups or len(groups) > MAX_LAYOUT_BLOCKS:
            raise ValueError(
                "First select each structure with its notes and use Edit > Group. "
                f"Arrange Scheme accepts 1–{MAX_LAYOUT_BLOCKS} existing groups."
            )
        self.setWindowTitle("Arrange Scheme")
        self.resize(900, min(700, max(440, len(groups) * 32 + 330)))
        self._source = source
        self._arrange = arrange
        self.result_report: dict[str, object] | None = None
        layout = QVBoxLayout(self)
        explanation = QLabel(
            "Each group is one structure block. Row 0 leaves a group unchanged. "
            "Choose note roles explicitly; none are guessed from their positions. "
            "Caption numbers are 1-based, in top-to-bottom order; other group notes keep their offsets. "
            "Put reaction conditions in the arrow's Above/Below labels, and keep panel explanations outside structure groups. "
            "Unassigned objects stay in place. Choose roles again after reopening this dialog. Arrange is one undoable edit."
        )
        explanation.setWordWrap(True)
        layout.addWidget(explanation)
        panel = QWidget(self)
        grid = QGridLayout(panel)
        for column, title in enumerate(
            (
                "Group",
                "Row (0 = skip)",
                "Order",
                "Note roles / caption order",
                "Arrow after",
                "Alignment group",
            )
        ):
            grid.addWidget(QLabel(title), 0, column)
        self.group_widgets: list[_GroupWidgets] = []
        for index, group in enumerate(groups):
            row = QSpinBox()
            row.setRange(0, MAX_LAYOUT_BLOCKS)
            row.setValue(1 if group["atoms"] else 0)
            row.setObjectName(f"schemeGroupRow{index}")
            order = QSpinBox()
            order.setRange(1, MAX_LAYOUT_BLOCKS)
            order.setValue(index + 1)
            notes = sorted(
                (i for kind, i in group["items"] if kind == "notes"),
            )
            captions = QLineEdit()
            captions.setPlaceholderText("No captions chosen")
            captions.setToolTip(
                "Comma-separated note numbers, in caption order. Empty means no captions.\n"
                + "\n".join(
                    f"{i + 1}: {_note_title(source['notes'][i])[:160]}" for i in notes
                )
            )
            arrow = QComboBox()
            arrow.addItem("None", None)
            for arrow_index, record in enumerate(source.get("arrows", [])):
                arrow.addItem(f"{arrow_index + 1}: {record['kind']}", arrow_index)
                labels = record.get("labels", {})
                arrow.setItemData(
                    arrow.count() - 1,
                    "\n".join(f"{side}: {text}" for side, text in labels.items())
                    or "No attached condition labels",
                    Qt.ItemDataRole.ToolTipRole,
                )
            column_group = QLineEdit()
            column_group.setPlaceholderText("Default")
            column_group.setMaxLength(64)
            column_group.setToolTip(
                "Rows with the same name share column widths. Use a different name for an independent row. "
                "Blank retains the original block-count alignment; wrapping uses independent lines."
            )
            widgets = _GroupWidgets(index, row, order, captions, arrow, column_group)
            self.group_widgets.append(widgets)
            roles = QWidget()
            role_layout = QHBoxLayout(roles)
            role_layout.setContentsMargins(0, 0, 0, 0)
            role_layout.addWidget(captions)
            choose_roles = QPushButton("Choose…")
            choose_roles.setEnabled(bool(notes))
            choose_roles.clicked.connect(
                lambda checked=False, entry=widgets: self._choose_note_roles(entry)
            )
            role_layout.addWidget(choose_roles)
            group_label = QLabel(
                f"{index + 1}: Structure ({len(group['atoms'])} atoms)"
            )
            group_label.setToolTip(
                f"Group {index + 1}: atom IDs {', '.join(str(a) for a in group['atoms'])}"
            )
            for column, widget in enumerate(
                (
                    group_label,
                    row,
                    order,
                    roles,
                    arrow,
                    column_group,
                )
            ):
                grid.addWidget(widget, index + 1, column)
        grid.setRowStretch(len(groups) + 1, 1)
        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setWidget(panel)
        layout.addWidget(scroll)
        form = QFormLayout()
        self.caption_alignment = QComboBox()
        self.caption_alignment.addItem("Shared caption baselines", "row")
        self.caption_alignment.addItem("Close to each structure", "structure")
        form.addRow("Caption placement", self.caption_alignment)
        self.arrow_color = QLineEdit()
        self.arrow_color.setPlaceholderText("Preserve colors; enter #000000 for black")
        self.arrow_color.setToolTip(
            "Only explicitly chosen connecting arrows and their labels are recolored. "
            "Font and stroke size retain the document settings."
        )
        form.addRow("Connecting-arrow color", self.arrow_color)
        self.distances: dict[str, QDoubleSpinBox] = {}
        for name, title, initial in (
            ("gap", "Horizontal gap", 40),
            ("row_gap", "Row gap", 30),
            ("caption_gap", "Structure–caption gap", 10),
            ("line_gap", "Caption-line gap", 4),
            ("max_row_width", "Wrap width (0 = no wrapping)", 0),
        ):
            spin = QDoubleSpinBox()
            spin.setRange(0, 100000 if name == "max_row_width" else 10000)
            spin.setDecimals(2)
            spin.setValue(initial)
            spin.setSuffix(" canvas units")
            spin.setObjectName(f"scheme_{name}")
            self.distances[name] = spin
            form.addRow(title, spin)
        layout.addLayout(form)
        self.error_label = QLabel()
        self.error_label.setWordWrap(True)
        self.error_label.setObjectName("schemeLayoutError")
        layout.addWidget(self.error_label)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        ok = buttons.button(QDialogButtonBox.StandardButton.Ok)
        assert ok is not None
        ok.setText("Arrange")
        buttons.accepted.connect(self._apply)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _choose_note_roles(self, widgets: _GroupWidgets) -> None:
        try:
            previous = tuple(
                int(value.strip()) - 1
                for value in widgets.captions.text().split(",")
                if value.strip()
            )
        except ValueError:
            self.error_label.setText(
                "Caption order must use note numbers, or clear it before choosing roles."
            )
            return
        notes = sorted(
            index
            for kind, index in self._source["groups"][widgets.index]["items"]
            if kind == "notes"
        )
        dialog = QDialog(self)
        dialog.setWindowTitle(f"Note roles — structure group {widgets.index + 1}")
        layout = QVBoxLayout(dialog)
        panel = QWidget(dialog)
        form = QFormLayout(panel)
        choices: dict[int, QComboBox] = {}
        for index in notes:
            role = QComboBox()
            role.addItem("Attached note — keep offset", "attached")
            role.addItem("Structure caption — place below", "caption")
            role.setCurrentIndex(1 if index in previous else 0)
            role.setObjectName(f"schemeNoteRole{index}")
            choices[index] = role
            title = _note_title(self._source["notes"][index])
            label = QLabel(f"{index + 1}: {title[:70]}")
            label.setToolTip(title)
            form.addRow(label, role)
        scroll = QScrollArea(dialog)
        scroll.setWidgetResizable(True)
        scroll.setWidget(panel)
        layout.addWidget(scroll)
        dialog.resize(600, min(650, 100 + len(notes) * 40))
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            selected = {
                index
                for index, role in choices.items()
                if role.currentData() == "caption"
            }
            ordered = list(
                dict.fromkeys(index for index in previous if index in selected)
            )
            ordered.extend(
                index for index in notes if index in selected and index not in ordered
            )
            widgets.captions.setText(", ".join(str(index + 1) for index in ordered))
        dialog.deleteLater()

    def _apply(self) -> None:
        try:
            choices = [
                GroupLayoutChoice(
                    widgets.index,
                    widgets.row.value(),
                    widgets.order.value(),
                    tuple(
                        int(value.strip()) - 1
                        for value in widgets.captions.text().split(",")
                        if value.strip()
                    )
                    if widgets.row.value()
                    else (),
                    widgets.arrow.currentData(),
                    widgets.column_group.text().strip() or None,
                )
                for widgets in self.group_widgets
            ]
            values = {name: spin.value() for name, spin in self.distances.items()}
            width = values.pop("max_row_width")
            request = grouped_layout_request(
                self._source,
                choices,
                max_row_width=width or None,
                caption_alignment=self.caption_alignment.currentData(),
                arrow_color=self.arrow_color.text().strip() or None,
                **values,
            )
            self.result_report = self._arrange(request)
        except Exception as exc:
            self.error_label.setText(str(exc) or "Could not arrange this drawing.")
            return
        self.accept()


def arrange_scheme_for_window(window) -> None:
    canvas = active_canvas_for_window(window)
    try:
        source, warnings = snapshot_canvas_document_state_with_warnings(canvas)
        if warnings:
            raise ValueError(
                "Resolve drawing snapshot warnings before arranging: "
                + "; ".join(warnings)
            )
        dialog = SchemeLayoutDialog(
            source,
            parent=window,
            arrange=lambda request: arrange_grouped_canvas(canvas, source, request),
        )
        if (
            dialog.exec() == QDialog.DialogCode.Accepted
            and dialog.result_report is not None
        ):
            report = dialog.result_report
            window.statusBar().showMessage(
                f"Arranged {report['block_count']} blocks in {report['row_count']} rows. Undo: Ctrl+Z.",
                6000,
            )
    except Exception as exc:
        QMessageBox.warning(window, "Arrange Scheme", str(exc))


__all__ = [
    "GroupLayoutChoice",
    "SchemeLayoutDialog",
    "arrange_grouped_canvas",
    "arrange_scheme_for_window",
    "grouped_layout_request",
]
