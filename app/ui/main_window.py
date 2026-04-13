import math

from PyQt6.QtCore import QPointF, QRectF, QSize, Qt, QTimer
from PyQt6.QtGui import (
    QAction,
    QActionGroup,
    QBrush,
    QColor,
    QFont,
    QIcon,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
    QPolygonF,
    QKeySequence,
)
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QColorDialog,
    QDockWidget,
    QFrame,
    QHBoxLayout,
    QLabel,
    QFileDialog,
    QLineEdit,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QToolButton,
    QSlider,
    QTabWidget,
    QToolBar,
    QVBoxLayout,
    QWidget,
    QDialog,
    QDoubleSpinBox,
)

from ui.canvas_view import CanvasView
from ui.main_window_path_logic import resolve_load_path, resolve_save_path


class ArrowButton(QToolButton):
    def __init__(self, direction: str, parent=None) -> None:
        super().__init__(parent)
        self._direction = direction
        self.setAutoRaise(True)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)

    def paintEvent(self, event) -> None:
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor("#3d3229"))
        rect = self.rect().adjusted(6, 4, -6, -4)
        if rect.width() <= 0 or rect.height() <= 0:
            return
        if self._direction == "up":
            points = [
                QPointF(rect.center().x(), rect.top()),
                QPointF(rect.right(), rect.bottom()),
                QPointF(rect.left(), rect.bottom()),
            ]
        else:
            points = [
                QPointF(rect.left(), rect.top()),
                QPointF(rect.right(), rect.top()),
                QPointF(rect.center().x(), rect.bottom()),
            ]
        painter.drawPolygon(QPolygonF(points))


class CornerMenuButton(QToolButton):
    def paintEvent(self, event) -> None:
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor("#8b7d6e"))
        rect = self.rect()
        size = 6
        right = rect.right() - 2
        bottom = rect.bottom() - 2
        left = right - size
        top = bottom - size
        points = [
            QPointF(right, bottom),
            QPointF(left, bottom),
            QPointF(right, top),
        ]
        painter.drawPolygon(QPolygonF(points))


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("LightDraw")
        self.resize(1100, 760)

        self.canvas = CanvasView()
        self.setCentralWidget(self.canvas)
        self.panel_tabs = None
        self.panel_dock = None
        self._current_file_path = None

        self._init_toolbars()
        # Info controls moved to top bar; no dock panels needed.
        self._apply_theme()
        self.canvas.setFrameStyle(0)

        self._zoom_label = QLabel("100%")
        self._zoom_label.setFixedWidth(50)
        self._zoom_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.statusBar().addPermanentWidget(self._zoom_label)
        self.canvas.set_zoom_callback(self._update_zoom_label)
        self.statusBar().showMessage("Ready")

    def _init_toolbars(self) -> None:
        tool_group = QActionGroup(self)
        tool_group.setExclusive(True)

        def tool_action(label: str, tool: str) -> QAction:
            action = QAction(label, self)
            action.setCheckable(True)
            action.triggered.connect(lambda: self._set_tool_with_status(tool))
            tool_group.addAction(action)
            return action

        left_bar = QToolBar("Tools", self)
        left_bar.setOrientation(Qt.Orientation.Vertical)
        left_bar.setMovable(False)
        left_bar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
        left_bar.setIconSize(QSize(26, 26))
        button_style = (
            "QToolButton {"
            " border: 1px solid transparent;"
            " border-radius: 5px;"
            " padding: 4px;"
            "}"
            "QToolButton:hover {"
            " background-color: #ebe4da;"
            " border-color: #d4c9bb;"
            "}"
            "QToolButton:pressed {"
            " background-color: #ddd3c5;"
            " border-color: #c4b6a4;"
            "}"
            "QToolButton:checked {"
            " background-color: #e8ddd0;"
            " border-color: #b8a48e;"
            "}"
        )
        menu_button_style = (
            "QToolButton {"
            " border: 1px solid transparent;"
            " border-radius: 5px;"
            " padding: 4px;"
            " padding-right: 4px;"
            "}"
            "QToolButton:hover {"
            " background-color: #ebe4da;"
            " border-color: #d4c9bb;"
            "}"
            "QToolButton:pressed {"
            " background-color: #ddd3c5;"
            " border-color: #c4b6a4;"
            "}"
            "QToolButton:checked {"
            " background-color: #e8ddd0;"
            " border-color: #b8a48e;"
            "}"
            "QToolButton::menu-indicator { image: none; width: 0px; }"
        )
        left_bar.setStyleSheet(button_style)

        action_select = tool_action("Select", "select")
        action_bond = tool_action("Bond", "bond")
        action_text = tool_action("Atom", "text")
        action_ring = tool_action("Ring", "benzene")
        action_arrow = tool_action("Arrow", "arrow")
        action_ts_bracket = tool_action("TS Bracket", "ts_bracket")
        action_perspective = tool_action("Perspective", "perspective")
        action_bond_bold = QAction("Bold Bond", self)
        action_bond_bold.setCheckable(True)
        action_bond_bold.setIcon(self._icon_bond_bold())
        action_bond_bold.triggered.connect(
            lambda: (self._set_tool_with_status("bond", reset_bond_style=False), self._set_bond_style("Bold"))
        )
        tool_group.addAction(action_bond_bold)
        action_wedge = QAction("Wedge", self)
        action_wedge.setCheckable(True)
        action_wedge.setIcon(self._icon_bond_wedge())
        action_wedge.triggered.connect(
            lambda: (self._set_tool_with_status("bond", reset_bond_style=False), self._set_bond_style("Wedge"))
        )
        tool_group.addAction(action_wedge)
        action_hash = QAction("Hash", self)
        action_hash.setCheckable(True)
        action_hash.setIcon(self._icon_bond_hash())
        action_hash.triggered.connect(
            lambda: (self._set_tool_with_status("bond", reset_bond_style=False), self._set_bond_style("Hash"))
        )
        tool_group.addAction(action_hash)
        action_mark_plus = QAction("Charge +", self)
        action_mark_plus.setCheckable(True)
        action_mark_plus.setIcon(self._icon_mark_plus())
        action_mark_plus.triggered.connect(
            lambda: (self.canvas.set_mark_kind("plus"), self.statusBar().showMessage("Mark Tool"))
        )
        tool_group.addAction(action_mark_plus)
        action_mark_minus = QAction("Charge -", self)
        action_mark_minus.setCheckable(True)
        action_mark_minus.setIcon(self._icon_mark_minus())
        action_mark_minus.triggered.connect(
            lambda: (self.canvas.set_mark_kind("minus"), self.statusBar().showMessage("Mark Tool"))
        )
        tool_group.addAction(action_mark_minus)
        action_mark_radical = QAction("Radical", self)
        action_mark_radical.setCheckable(True)
        action_mark_radical.setIcon(self._icon_mark_radical())
        action_mark_radical.triggered.connect(
            lambda: (self.canvas.set_mark_kind("radical"), self.statusBar().showMessage("Mark Tool"))
        )
        tool_group.addAction(action_mark_radical)
        self._tool_actions = {
            "select": action_select,
            "bond": action_bond,
            "bond_bold": action_bond_bold,
            "bond_wedge": action_wedge,
            "bond_hash": action_hash,
            "text": action_text,
            "mark_plus": action_mark_plus,
            "mark_minus": action_mark_minus,
            "mark_radical": action_mark_radical,
            "benzene": action_ring,
            "arrow": action_arrow,
            "ts_bracket": action_ts_bracket,
            "perspective": action_perspective,
        }

        action_select.setIcon(self._icon_select())
        action_select.setToolTip("Select / Marquee (ChemDraw: Space)")
        action_bond.setIcon(self._icon_bond())
        action_bond.setToolTip("Bond (ChemDraw: X)")
        action_text.setIcon(self._icon_text())
        action_text.setToolTip("Atom / Text (ChemDraw: T)")
        action_ring.setIcon(self._icon_ring())
        action_ring.setToolTip("Ring / Benzene (ChemDraw: J)")
        action_arrow.setIcon(self._icon_arrow())
        action_arrow.setToolTip("Arrow (ChemDraw: E)")
        action_ts_bracket.setIcon(self._icon_ts_bracket())
        action_ts_bracket.setToolTip("TS Bracket (ChemDraw: Shift+G)")
        action_perspective.setIcon(self._icon_perspective())
        action_perspective.setToolTip("Perspective Rotation (ChemDraw: Alt+D, Shift+drag locks X/Y)")
        action_bond_bold.setToolTip("Bold Bond (Bond Hotkey: B)")
        action_wedge.setToolTip("Wedge Bond (Bond Hotkey: W)")
        action_hash.setToolTip("Hash Bond (Bond Hotkey: Shift+H)")
        action_mark_plus.setToolTip("Charge + (Atom Hotkey: +)")
        action_mark_minus.setToolTip("Charge - (Atom Hotkey: -)")
        action_mark_radical.setToolTip("Radical")

        left_bar.addAction(action_select)
        left_bar.addAction(action_perspective)
        left_bar.addAction(action_bond)
        left_bar.addAction(action_bond_bold)
        left_bar.addAction(action_wedge)
        left_bar.addAction(action_hash)
        left_bar.addAction(action_text)
        left_bar.addAction(action_mark_plus)
        left_bar.addAction(action_mark_minus)
        left_bar.addAction(action_mark_radical)
        left_bar.addAction(action_ring)
        templates_button = CornerMenuButton()
        templates_button.setIcon(self._icon_templates())
        templates_button.setToolTip("Templates")
        templates_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        templates_button.setStyleSheet(menu_button_style)
        templates_menu = QMenu(templates_button)
        for label, handler in self._template_entries():
            templates_menu.addAction(self._icon_template_preview(label), label, handler)
        templates_button.setMenu(templates_menu)
        left_bar.addWidget(templates_button)
        arrow_button = CornerMenuButton()
        arrow_button.setDefaultAction(action_arrow)
        arrow_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        arrow_button.setStyleSheet(menu_button_style)
        arrow_menu = QMenu(arrow_button)
        for label, kind in [
            ("Reaction", "reaction"),
            ("Equilibrium", "equilibrium"),
            ("Resonance", "resonance"),
            ("Curved Single", "curved_single"),
            ("Curved Double", "curved_double"),
            ("Inhibition", "inhibit"),
            ("Dotted", "dotted"),
        ]:
            action = arrow_menu.addAction(self._icon_arrow_preview(kind), label)
            action.triggered.connect(
                lambda checked=False, value=label: (
                    self._set_tool_with_status("arrow"),
                    self._set_arrow_type(value),
                )
            )
        preset_menu = arrow_menu.addMenu("Preset")
        for label in ["ACS", "Bold", "Fine"]:
            action = preset_menu.addAction(label)
            action.triggered.connect(
                lambda checked=False, value=label: (
                    self._set_tool_with_status("arrow"),
                    self._set_arrow_preset(value),
                )
            )
        arrow_menu.addSeparator()
        arrow_menu.addAction("Settings...").triggered.connect(self._open_arrow_settings)
        arrow_button.setMenu(arrow_menu)

        left_bar.addWidget(arrow_button)
        left_bar.addAction(action_ts_bracket)

        bond_len_btn = QToolButton()
        bond_len_btn.setToolTip("Bond Length")
        bond_len_btn.setIcon(self._icon_bond_length())
        bond_len_btn.clicked.connect(self._set_bond_length)

        flip_h = QToolButton()
        flip_h.setToolTip("Flip Horizontal (Ctrl+Shift+H)")
        flip_h.setIcon(self._icon_flip_h())
        flip_h.clicked.connect(self.canvas.flip_horizontal)
        flip_v = QToolButton()
        flip_v.setToolTip("Flip Vertical (Ctrl+Shift+V)")
        flip_v.setIcon(self._icon_flip_v())
        flip_v.clicked.connect(self.canvas.flip_vertical)

        left_bar.addWidget(flip_h)
        left_bar.addWidget(flip_v)

        self.addToolBar(Qt.ToolBarArea.LeftToolBarArea, left_bar)
        action_bond.setChecked(True)

        panel_bar = QToolBar("Panels", self)
        panel_bar.setMovable(False)
        panel_bar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
        panel_bar.setIconSize(QSize(24, 24))
        panel_bar.setStyleSheet(button_style)

        save_btn = QToolButton()
        save_btn.setIcon(self._icon_save())
        save_btn.setToolTip("Save")
        save_btn.setShortcut(QKeySequence.StandardKey.Save)
        save_btn.clicked.connect(self._save_canvas)

        load_btn = QToolButton()
        load_btn.setIcon(self._icon_open())
        load_btn.setToolTip("Load")
        load_btn.setShortcut(QKeySequence.StandardKey.Open)
        load_btn.clicked.connect(self._load_canvas)

        undo_btn = QToolButton()
        undo_btn.setIcon(self._icon_undo())
        undo_btn.setToolTip("Undo")
        undo_btn.setShortcut(QKeySequence.StandardKey.Undo)
        undo_btn.clicked.connect(self.canvas.undo)

        redo_btn = QToolButton()
        redo_btn.setIcon(self._icon_redo())
        redo_btn.setToolTip("Redo")
        redo_btn.setShortcut(QKeySequence.StandardKey.Redo)
        redo_btn.clicked.connect(self.canvas.redo)

        smiles_input = QLineEdit()
        smiles_input.setPlaceholderText("SMILES...")
        smiles_input.setFixedWidth(180)
        smiles_button = QToolButton()
        smiles_button.setText("Render")
        smiles_button.setAutoRaise(False)
        smiles_button.setCursor(Qt.CursorShape.PointingHandCursor)
        smiles_button.setObjectName("smiles_render_button")
        smiles_button.setStyleSheet(
            "QToolButton#smiles_render_button {"
            " border: 1px solid #d4c9bb;"
            " border-radius: 5px;"
            " padding: 3px 10px;"
            " background-color: #faf8f5;"
            " color: #3d3229;"
            "}"
            "QToolButton#smiles_render_button:hover {"
            " background-color: #ebe4da;"
            " border-color: #c4b6a4;"
            "}"
            "QToolButton#smiles_render_button:pressed {"
            " background-color: #ddd3c5;"
            " border-color: #b8a48e;"
            "}"
        )
        smiles_button.clicked.connect(lambda: self.canvas.begin_smiles_insert(smiles_input.text()))
        smiles_input.returnPressed.connect(lambda: self.canvas.begin_smiles_insert(smiles_input.text()))

        panel_bar.addWidget(save_btn)
        panel_bar.addWidget(load_btn)
        panel_bar.addSeparator()
        panel_bar.addWidget(undo_btn)
        panel_bar.addWidget(redo_btn)
        panel_bar.addSeparator()
        panel_bar.addWidget(smiles_input)
        panel_bar.addWidget(smiles_button)
        panel_bar.addSeparator()
        atom_input = QLineEdit()
        atom_input.setPlaceholderText("Atom")
        atom_input.setFixedWidth(60)
        atom_input.setMaxLength(4)
        atom_input.setText(self.canvas.get_atom_symbol())
        atom_input.textChanged.connect(self.canvas.set_atom_symbol)
        panel_bar.addWidget(atom_input)
        color_button = CornerMenuButton()
        color_button.setIcon(self._icon_color())
        color_button.setToolTip("Color")
        color_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        color_button.setStyleSheet(menu_button_style)
        color_menu = QMenu(color_button)
        for label, hex_value in self._acs_color_palette():
            pixmap = QPixmap(16, 16)
            pixmap.fill(QColor(hex_value))
            color_action = color_menu.addAction(QIcon(pixmap), label)
            color_action.triggered.connect(lambda checked=False, c=hex_value: self._apply_color_preset(c))
        color_button.setMenu(color_menu)
        panel_bar.addWidget(color_button)

        ring_fill_button = CornerMenuButton()
        ring_fill_button.setIcon(self._icon_ring_fill())
        ring_fill_button.setToolTip("Ring Fill")
        ring_fill_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        ring_fill_button.setStyleSheet(menu_button_style)
        ring_fill_menu = QMenu(ring_fill_button)
        for label, hex_value in self._acs_color_palette():
            pixmap = QPixmap(16, 16)
            pixmap.fill(QColor(hex_value))
            fill_action = ring_fill_menu.addAction(QIcon(pixmap), label)
            fill_action.triggered.connect(lambda checked=False, c=hex_value: self._apply_ring_fill_preset(c))
        ring_fill_button.setMenu(ring_fill_menu)
        panel_bar.addWidget(ring_fill_button)
        panel_bar.addWidget(bond_len_btn)
        panel_bar.addSeparator()

        formula_label = QLabel("Formula")
        formula_value = QLineEdit()
        formula_value.setReadOnly(True)
        formula_value.setFixedWidth(140)
        formula_value.setPlaceholderText(" ")
        mw_label = QLabel("MW")
        mw_value = QLineEdit()
        mw_value.setReadOnly(True)
        mw_value.setFixedWidth(100)
        mw_value.setPlaceholderText(" ")
        panel_bar.addWidget(formula_label)
        panel_bar.addWidget(formula_value)
        panel_bar.addWidget(mw_label)
        panel_bar.addWidget(mw_value)
        panel_bar.addSeparator()

        self.addToolBar(Qt.ToolBarArea.TopToolBarArea, panel_bar)

        def _update_selection_info(formula: str, mw: str) -> None:
            formula_value.setText(formula)
            mw_value.setText(mw)

        self.canvas.set_selection_info_callback(_update_selection_info)
        self.canvas.set_tool_change_callback(self._sync_tool_actions_from_canvas)
        self._sync_tool_actions_from_canvas()

    def _make_icon(self, painter_fn) -> QIcon:
        pixmap = QPixmap(30, 30)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter_fn(painter)
        painter.end()
        return QIcon(pixmap)

    def _icon_select(self) -> QIcon:
        def draw(p):
            pen = QPen(QColor("#8b7355"))
            pen.setWidthF(2.0)
            pen.setStyle(Qt.PenStyle.DashLine)
            p.setPen(pen)
            p.drawRect(5, 6, 20, 18)
        return self._make_icon(draw)

    def _icon_bond(self) -> QIcon:
        def draw(p):
            pen = QPen(QColor("#3d3229"))
            pen.setWidthF(2.0)
            p.setPen(pen)
            p.drawLine(7, 23, 23, 7)
        return self._make_icon(draw)

    def _icon_bond_bold(self) -> QIcon:
        def draw(p):
            start = QPointF(6, 23)
            end = QPointF(24, 7)
            dx = end.x() - start.x()
            dy = end.y() - start.y()
            start = QPointF(start.x() + dx * 0.025, start.y() + dy * 0.025)
            end = QPointF(end.x() - dx * 0.025, end.y() - dy * 0.025)
            p.setPen(self.canvas.renderer.bold_bond_pen())
            p.drawLine(start, end)
        return self._make_icon(draw)

    def _icon_mark_plus(self) -> QIcon:
        def draw(p):
            pen = QPen(QColor("#c00000"))
            pen.setWidthF(2.0)
            p.setPen(pen)
            p.drawLine(15, 7, 15, 23)
            p.drawLine(7, 15, 23, 15)
        return self._make_icon(draw)

    def _icon_mark_minus(self) -> QIcon:
        def draw(p):
            pen = QPen(QColor("#1f5eff"))
            pen.setWidthF(2.0)
            p.setPen(pen)
            p.drawLine(7, 15, 23, 15)
        return self._make_icon(draw)

    def _icon_mark_radical(self) -> QIcon:
        def draw(p):
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor("#6a2ea6"))
            p.drawEllipse(12, 12, 6, 6)
        return self._make_icon(draw)

    def _icon_text(self) -> QIcon:
        def draw(p):
            font = QFont("Arial")
            font.setBold(True)
            font.setPointSize(22)
            p.setFont(font)
            p.setPen(QPen(QColor("#3d3229")))
            p.drawText(7, 21, "A")
        return self._make_icon(draw)

    def _icon_ring(self) -> QIcon:
        def draw(p):
            p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            pen = QPen(QColor("#3d3229"))
            pen.setWidthF(1.8)
            p.setPen(pen)
            center = QPointF(15.0, 15.0)
            radius = 10.0
            outer = QPolygonF()
            for i in range(6):
                angle = math.radians(60 * i - 90)
                outer.append(
                    QPointF(
                        center.x() + radius * math.cos(angle),
                        center.y() + radius * math.sin(angle),
                    )
                )
            p.drawPolygon(outer)
            inner_pen = QPen(QColor("#3d3229"))
            inner_pen.setWidthF(1.8)
            p.setPen(inner_pen)
            spacing = 1.6
            for i in range(0, 6, 2):
                a = outer[i]
                b = outer[(i + 1) % 6]
                dx = b.x() - a.x()
                dy = b.y() - a.y()
                length = math.hypot(dx, dy) or 1.0
                ux = dx / length
                uy = dy / length
                nx = -dy / length
                ny = dx / length
                mid_x = (a.x() + b.x()) / 2.0
                mid_y = (a.y() + b.y()) / 2.0
                to_cx = center.x() - mid_x
                to_cy = center.y() - mid_y
                if nx * to_cx + ny * to_cy < 0:
                    nx = -nx
                    ny = -ny
                trim = max(1.2, length * 0.12)
                p1 = QPointF(a.x() + ux * trim + nx * spacing, a.y() + uy * trim + ny * spacing)
                p2 = QPointF(b.x() - ux * trim + nx * spacing, b.y() - uy * trim + ny * spacing)
                p.drawLine(p1, p2)
        return self._make_icon(draw)

    def _icon_ring_fill(self) -> QIcon:
        def draw(p):
            p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            pen = QPen(QColor("#3d3229"))
            pen.setWidthF(1.8)
            center = QPointF(15.0, 15.0)
            radius = 10.0
            outer = QPolygonF()
            for i in range(5):
                angle = math.radians(360 / 5 * i - 90)
                outer.append(
                    QPointF(
                        center.x() + radius * math.cos(angle),
                        center.y() + radius * math.sin(angle),
                    )
                )
            p.setPen(pen)
            p.setBrush(QBrush(QColor("#f3ead7")))
            p.drawPolygon(outer)
        return self._make_icon(draw)

    def _icon_undo(self) -> QIcon:
        def draw(p):
            pen = QPen(QColor("#3d3229"))
            pen.setWidthF(1.6)
            p.setPen(pen)
            p.drawArc(5, 8, 18, 18, 90 * 16, 270 * 16)
            p.drawLine(8, 10, 5, 15)
            p.drawLine(8, 10, 11, 10)
        return self._make_icon(draw)

    def _icon_redo(self) -> QIcon:
        def draw(p):
            pen = QPen(QColor("#3d3229"))
            pen.setWidthF(1.6)
            p.setPen(pen)
            p.drawArc(8, 8, 18, 18, 180 * 16, 270 * 16)
            p.drawLine(23, 10, 25, 15)
            p.drawLine(23, 10, 19, 10)
        return self._make_icon(draw)

    def _icon_save(self) -> QIcon:
        def draw(p):
            pen = QPen(QColor("#3d3229"))
            pen.setWidthF(1.4)
            p.setPen(pen)
            p.drawRect(6, 5, 18, 20)
            p.drawLine(6, 11, 24, 11)
            p.drawRect(10, 15, 10, 8)
        return self._make_icon(draw)

    def _icon_open(self) -> QIcon:
        def draw(p):
            pen = QPen(QColor("#3d3229"))
            pen.setWidthF(1.4)
            p.setPen(pen)
            p.drawRect(6, 13, 18, 10)
            p.drawLine(15, 6, 15, 16)
            p.drawLine(11, 10, 15, 6)
            p.drawLine(19, 10, 15, 6)
        return self._make_icon(draw)

    def _icon_templates(self) -> QIcon:
        def draw(p):
            pen = QPen(QColor("#3d3229"))
            pen.setWidthF(1.6)
            p.setPen(pen)
            chair = self._chair_icon_points(QRectF(4.0, 7.0, 22.0, 16.0))
            if not chair.isEmpty():
                p.drawPolygon(chair)
        return self._make_icon(draw)

    def _icon_info(self) -> QIcon:
        def draw(p):
            pen = QPen(QColor("#3d3229"))
            pen.setWidthF(1.4)
            p.setPen(pen)
            p.drawEllipse(7, 7, 16, 16)
            p.drawLine(15, 13, 15, 19)
            p.drawPoint(15, 10)
        return self._make_icon(draw)

    def _icon_bond_double(self) -> QIcon:
        def draw(p):
            pen = QPen(QColor("#3d3229"))
            pen.setWidthF(1.6)
            p.setPen(pen)
            p.drawLine(5, 11, 25, 11)
            p.drawLine(5, 19, 25, 19)
        return self._make_icon(draw)

    def _icon_bond_triple(self) -> QIcon:
        def draw(p):
            pen = QPen(QColor("#3d3229"))
            pen.setWidthF(1.4)
            p.setPen(pen)
            p.drawLine(5, 10, 25, 10)
            p.drawLine(5, 15, 25, 15)
            p.drawLine(5, 20, 25, 20)
        return self._make_icon(draw)

    def _icon_bond_wedge(self) -> QIcon:
        def draw(p):
            start = QPointF(7, 23)
            end = QPointF(23, 7)
            dx = end.x() - start.x()
            dy = end.y() - start.y()
            start = QPointF(start.x() + dx * 0.1, start.y() + dy * 0.1)
            dx = end.x() - start.x()
            dy = end.y() - start.y()
            length = math.hypot(dx, dy) or 1.0
            nx = -dy / length
            ny = dx / length
            half_width = self.canvas.renderer.bold_bond_pen().widthF() * 0.5 * 0.95
            p1 = start
            p2 = QPointF(end.x() + nx * half_width, end.y() + ny * half_width)
            p3 = QPointF(end.x() - nx * half_width, end.y() - ny * half_width)
            polygon = QPolygonF([p1, p2, p3])
            p.setPen(self.canvas.renderer.bond_pen())
            p.setBrush(QBrush(QColor(self.canvas.renderer.style.bond_color)))
            p.drawPolygon(polygon)
        return self._make_icon(draw)

    def _icon_bond_hash(self) -> QIcon:
        def draw(p):
            start = QPointF(7, 23)
            end = QPointF(23, 7)
            dx = end.x() - start.x()
            dy = end.y() - start.y()
            length = math.hypot(dx, dy) or 1.0
            nx = -dy / length
            ny = dx / length
            count = max(3, int(length / self.canvas.renderer.style.hash_spacing_px))
            max_size = self.canvas.renderer.bold_bond_pen().widthF()
            if count <= 1:
                t_positions = [0.5]
                t_sizes = [1.0]
            else:
                t_positions = [i / (count - 1) for i in range(count)]
                t_sizes = [(i + 1) / (count + 1) for i in range(count)]
            max_t = max(t_sizes) if t_sizes else 1.0
            p.setPen(self.canvas.renderer.bond_pen())
            for t_pos, t_size in zip(t_positions, t_sizes):
                cx = start.x() + dx * t_pos
                cy = start.y() + dy * t_pos
                size = max_size * (t_size / max_t) if max_t > 0 else max_size
                hx = nx * size / 2.0
                hy = ny * size / 2.0
                p.drawLine(QPointF(cx - hx, cy - hy), QPointF(cx + hx, cy + hy))
        return self._make_icon(draw)

    def _icon_bond_length(self) -> QIcon:
        def draw(p):
            pen = QPen(QColor("#3d3229"))
            pen.setWidthF(1.4)
            p.setPen(pen)
            p.drawLine(6, 15, 24, 15)
            p.drawLine(6, 11, 6, 19)
            p.drawLine(24, 11, 24, 19)
        return self._make_icon(draw)

    def _icon_arrow_preview(self, kind: str) -> QIcon:
        def draw(p):
            pen = QPen(QColor("#3d3229"))
            pen.setWidthF(1.4)
            if kind == "dotted":
                pen.setStyle(Qt.PenStyle.DashLine)
            p.setPen(pen)
            if kind in {"curved_single", "curved_double"}:
                path = QPainterPath()
                path.moveTo(6, 19)
                path.quadTo(15, 6, 24, 15)
                p.drawPath(path)
                self._draw_arrow_head(p, QPointF(15, 8), QPointF(24, 15))
                if kind == "curved_double":
                    self._draw_arrow_head(p, QPointF(15, 8), QPointF(6, 19))
            elif kind == "equilibrium":
                p.drawLine(5, 11, 23, 11)
                self._draw_arrow_head(p, QPointF(5, 11), QPointF(23, 11))
                p.drawLine(23, 19, 5, 19)
                self._draw_arrow_head(p, QPointF(23, 19), QPointF(5, 19))
            elif kind == "resonance":
                p.drawLine(5, 15, 23, 15)
                self._draw_arrow_head(p, QPointF(5, 15), QPointF(23, 15))
                self._draw_arrow_head(p, QPointF(23, 15), QPointF(5, 15))
            elif kind == "inhibit":
                p.drawLine(5, 15, 23, 15)
                p.drawLine(23, 10, 23, 20)
            else:
                p.drawLine(5, 15, 23, 15)
                self._draw_arrow_head(p, QPointF(5, 15), QPointF(23, 15))
        return self._make_icon(draw)

    def _draw_arrow_head(self, painter: QPainter, start: QPointF, end: QPointF) -> None:
        angle = math.atan2(end.y() - start.y(), end.x() - start.x())
        head_len = 4.5
        head_angle = math.radians(25)
        left = QPointF(
            end.x() - head_len * math.cos(angle - head_angle),
            end.y() - head_len * math.sin(angle - head_angle),
        )
        right = QPointF(
            end.x() - head_len * math.cos(angle + head_angle),
            end.y() - head_len * math.sin(angle + head_angle),
        )
        painter.drawLine(left, end)
        painter.drawLine(right, end)

    def _icon_orbital_preview(self, kind: str) -> QIcon:
        def draw(p):
            pen = QPen(QColor("#3d3229"))
            pen.setWidthF(1.4)
            p.setPen(pen)
            if kind == "s":
                p.drawEllipse(9, 9, 12, 12)
            elif kind == "p":
                p.drawEllipse(6, 11, 10, 10)
                p.drawEllipse(14, 9, 10, 10)
            elif kind == "sp":
                p.drawEllipse(6, 12, 10, 10)
                p.drawEllipse(16, 8, 10, 10)
                p.drawLine(5, 18, 25, 12)
            elif kind in {"sp2", "sp3"}:
                p.drawEllipse(7, 7, 8, 8)
                p.drawEllipse(15, 7, 8, 8)
                p.drawEllipse(11, 15, 8, 8)
                if kind == "sp3":
                    p.drawEllipse(11, 2, 8, 8)
            elif kind == "d":
                p.drawEllipse(6, 10, 8, 8)
                p.drawEllipse(16, 10, 8, 8)
                p.drawEllipse(11, 5, 8, 8)
                p.drawEllipse(11, 15, 8, 8)
            else:
                p.drawEllipse(9, 9, 12, 12)
                p.drawLine(15, 9, 15, 21)
        return self._make_icon(draw)

    def _icon_template_preview(self, label: str) -> QIcon:
        def draw_ring(p, sides: int):
            center = QPointF(15.0, 15.0)
            radius = 10.0
            poly = QPolygonF()
            for i in range(sides):
                angle = math.radians(360 / sides * i - 90)
                poly.append(
                    QPointF(
                        center.x() + radius * math.cos(angle),
                        center.y() + radius * math.sin(angle),
                    )
                )
            p.drawPolygon(poly)

        def draw(p):
            pen = QPen(QColor("#3d3229"))
            pen.setWidthF(1.4)
            p.setPen(pen)
            lower = label.lower()
            if "cyclopropane" in lower:
                draw_ring(p, 3)
            elif "cyclobutane" in lower:
                draw_ring(p, 4)
            elif "cyclopentane" in lower or "furan" in lower or "thiophene" in lower:
                draw_ring(p, 5)
            elif "benzene" in lower or "pyridine" in lower or "pyrimidine" in lower:
                draw_ring(p, 6)
            elif "naphthalene" in lower or "anthracene" in lower or "phenanthrene" in lower:
                draw_ring(p, 6)
                draw_ring(p, 6)
                p.drawLine(12, 7, 18, 7)
            elif "crown" in lower:
                draw_ring(p, 10)
            elif "chair" in lower:
                chair = self._chair_icon_points(QRectF(4.0, 7.0, 22.0, 16.0))
                if not chair.isEmpty():
                    p.drawPolygon(chair)
            elif label in {"Me", "Et", "t-Bu", "i-Pr"}:
                p.drawLine(5, 15, 15, 15)
                p.drawText(16, 18, label)
            elif label in {"Vinyl", "Allyl"}:
                p.drawLine(5, 18, 14, 12)
                p.drawLine(14, 12, 23, 18)
            elif label in {"Carboxyl", "Carbonyl"}:
                p.drawLine(5, 15, 15, 15)
                p.drawLine(15, 15, 23, 10)
                p.drawText(23, 12, "O")
            elif label in {"Nitro", "Sulfonyl"}:
                p.drawLine(5, 15, 15, 15)
                p.drawText(16, 18, "NO2" if label == "Nitro" else "SO2")
            else:
                draw_ring(p, 6)
        return self._make_icon(draw)

    def _chair_icon_points(self, rect: QRectF) -> QPolygonF:
        angle_steep = math.radians(-68.0)
        angle_shallow = math.radians(-25.0)
        v1 = QPointF(math.cos(angle_steep), math.sin(angle_steep))
        v2 = QPointF(math.cos(angle_shallow), math.sin(angle_shallow))

        points = [
            QPointF(0.0, 0.0),
            QPointF(v1.x(), v1.y()),
            QPointF(v1.x() + 1.0, v1.y()),
            QPointF(v1.x() + 1.0 + v2.x(), v1.y() + v2.y()),
            QPointF(1.0 + v2.x(), v2.y()),
            QPointF(v2.x(), v2.y()),
        ]
        min_x = min(point.x() for point in points)
        max_x = max(point.x() for point in points)
        min_y = min(point.y() for point in points)
        max_y = max(point.y() for point in points)
        width = max_x - min_x
        height = max_y - min_y
        if width <= 1e-6 or height <= 1e-6:
            return QPolygonF()
        scale = min(rect.width() / width, rect.height() / height) * 0.92
        cx = (min_x + max_x) / 2.0
        cy = (min_y + max_y) / 2.0
        center = rect.center()
        poly = QPolygonF()
        for point in points:
            poly.append(
                QPointF(
                    center.x() + (point.x() - cx) * scale,
                    center.y() + (point.y() - cy) * scale,
                )
            )
        return poly

    def _icon_flip_h(self) -> QIcon:
        def draw(p):
            pen = QPen(QColor("#3d3229"))
            pen.setWidthF(1.4)
            p.setPen(pen)
            p.drawLine(15, 5, 15, 25)
            p.drawLine(7, 9, 13, 9)
            p.drawLine(7, 21, 13, 21)
            p.drawLine(17, 9, 23, 9)
            p.drawLine(17, 21, 23, 21)
        return self._make_icon(draw)

    def _icon_flip_v(self) -> QIcon:
        def draw(p):
            pen = QPen(QColor("#3d3229"))
            pen.setWidthF(1.4)
            p.setPen(pen)
            p.drawLine(5, 15, 25, 15)
            p.drawLine(9, 7, 9, 13)
            p.drawLine(21, 7, 21, 13)
            p.drawLine(9, 17, 9, 23)
            p.drawLine(21, 17, 21, 23)
        return self._make_icon(draw)

    def _icon_arrow(self) -> QIcon:
        def draw(p):
            pen = QPen(QColor("#3d3229"))
            pen.setWidthF(2.0)
            p.setPen(pen)
            p.drawLine(5, 15, 23, 15)
            p.drawLine(23, 15, 18, 11)
            p.drawLine(23, 15, 18, 19)
        return self._make_icon(draw)

    def _icon_ts_bracket(self) -> QIcon:
        def draw(p):
            pen = QPen(QColor("#3d3229"))
            pen.setWidthF(1.0)
            p.setPen(pen)
            p.drawLine(8, 7, 5, 7)
            p.drawLine(5, 7, 5, 23)
            p.drawLine(5, 23, 8, 23)
            p.drawLine(22, 7, 25, 7)
            p.drawLine(25, 7, 25, 23)
            p.drawLine(25, 23, 22, 23)
            font = p.font()
            font.setPixelSize(8)
            p.setFont(font)
            p.drawText(QRectF(10.0, 8.0, 12.0, 8.0), Qt.AlignmentFlag.AlignCenter, "TS")
        return self._make_icon(draw)

    def _icon_orbital(self) -> QIcon:
        def draw(p):
            pen = QPen(QColor("#3d3229"))
            pen.setWidthF(1.4)
            p.setPen(pen)
            p.drawEllipse(6, 10, 8, 10)
            p.drawEllipse(16, 10, 8, 10)
        return self._make_icon(draw)

    def _icon_move(self) -> QIcon:
        def draw(p):
            pen = QPen(QColor("#3d3229"))
            pen.setWidthF(1.4)
            p.setPen(pen)
            p.drawLine(15, 5, 15, 25)
            p.drawLine(5, 15, 25, 15)
            p.drawLine(15, 5, 12, 8)
            p.drawLine(15, 5, 18, 8)
            p.drawLine(15, 25, 12, 22)
            p.drawLine(15, 25, 18, 22)
            p.drawLine(5, 15, 8, 12)
            p.drawLine(5, 15, 8, 18)
            p.drawLine(25, 15, 22, 12)
            p.drawLine(25, 15, 22, 18)
        return self._make_icon(draw)

    def _icon_color(self) -> QIcon:
        def draw(p):
            pen = QPen(QColor("#3d3229"))
            pen.setWidthF(1.4)
            p.setPen(pen)
            p.setBrush(QBrush(QColor("#d8c8a6")))
            palette = QPainterPath()
            palette.moveTo(4, 18)
            palette.cubicTo(4, 8, 15, 6, 25, 9)
            palette.cubicTo(29, 10, 29, 20, 23, 24)
            palette.cubicTo(18, 26, 11, 25, 9, 21)
            palette.cubicTo(14, 23, 15, 20, 14, 18)
            palette.cubicTo(11, 20, 6, 20, 4, 18)
            p.drawPath(palette)
            p.setBrush(QBrush(Qt.GlobalColor.white))
            p.drawEllipse(9, 13, 4, 4)
            p.drawEllipse(14, 11, 4, 4)
            p.drawEllipse(19, 15, 4, 4)
        return self._make_icon(draw)

    def _icon_perspective(self) -> QIcon:
        def draw(p):
            pen = QPen(QColor("#3d3229"))
            pen.setWidthF(1.4)
            p.setPen(pen)
            cx, cy, r = 15.0, 15.0, 10.0
            start_deg = 40.0
            span_deg = 280.0
            end_deg = (start_deg + span_deg) % 360.0
            p.drawArc(5, 5, 20, 20, int(start_deg * 16), int(span_deg * 16))
            rad = math.radians(end_deg)
            end = QPointF(cx + r * math.cos(rad), cy - r * math.sin(rad))
            tangent = rad + math.pi / 2.0
            head_len = 3.0
            head_angle = math.radians(25.0)
            left = QPointF(
                end.x() + head_len * math.cos(tangent + math.pi + head_angle),
                end.y() - head_len * math.sin(tangent + math.pi + head_angle),
            )
            right = QPointF(
                end.x() + head_len * math.cos(tangent + math.pi - head_angle),
                end.y() - head_len * math.sin(tangent + math.pi - head_angle),
            )
            p.drawLine(end, left)
            p.drawLine(end, right)
        return self._make_icon(draw)

    def _init_panels(self) -> None:
        dock = QDockWidget("Panels", self)
        dock.setFeatures(QDockWidget.DockWidgetFeature.DockWidgetClosable)
        dock.setAllowedAreas(Qt.DockWidgetArea.LeftDockWidgetArea | Qt.DockWidgetArea.RightDockWidgetArea)
        dock.setMinimumWidth(260)
        dock.setMaximumWidth(360)

        tabs = QTabWidget()
        tabs.addTab(self._build_mark_panel(), "Charge")

        dock.setWidget(tabs)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, dock)
        self.panel_tabs = tabs
        self.panel_dock = dock

    def _build_mark_panel(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        title = QLabel("Charges")
        title.setStyleSheet("font-weight: 600;")
        layout.addWidget(title)

        for label, kind in (
            ("+ Charge", "plus"),
            ("- Charge", "minus"),
            ("Radical", "radical"),
        ):
            button = QPushButton(label)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.clicked.connect(lambda checked=False, k=kind: self.canvas.set_mark_kind(k))
            layout.addWidget(button)

        hint = QLabel("Click an atom or canvas to place.")
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #555555;")
        layout.addWidget(hint)
        layout.addStretch(1)
        return panel

    def _show_panel(self, index: int) -> None:
        if self.panel_tabs is None or self.panel_dock is None:
            return
        self.panel_tabs.setCurrentIndex(index)
        self.panel_dock.show()
        self.panel_dock.raise_()

    def _apply_theme(self) -> None:
        self.setStyleSheet(
            """
            QMainWindow {
                background: #f0ebe4;
            }
            QToolBar {
                background: #f7f3ee;
                border: none;
                border-bottom: 1px solid #ddd5ca;
                spacing: 4px;
                padding: 3px;
            }
            QToolBar::separator {
                background: #ddd5ca;
                width: 1px;
                height: 20px;
                margin: 4px 6px;
            }
            QToolButton {
                border: 1px solid transparent;
                border-radius: 5px;
                padding: 5px;
                color: #3d3229;
            }
            QToolButton:hover {
                background: #ebe4da;
                border-color: #d4c9bb;
            }
            QToolButton:pressed {
                background: #ddd3c5;
                border-color: #c4b6a4;
            }
            QToolButton:checked {
                background: #e8ddd0;
                border-color: #b8a48e;
            }
            QLabel, QCheckBox, QGroupBox, QTabBar, QDockWidget, QToolButton {
                color: #3d3229;
            }
            QDockWidget {
                background: #f7f3ee;
                border: 1px solid #ddd5ca;
            }
            QTabWidget::pane {
                border: 1px solid #ddd5ca;
                background: #f7f3ee;
            }
            QTabBar::tab {
                background: #f0ebe4;
                padding: 6px 10px;
                border: 1px solid #ddd5ca;
                border-bottom: none;
                margin-right: 2px;
                color: #3d3229;
            }
            QTabBar::tab:selected {
                background: #faf8f5;
            }
            QLineEdit, QComboBox, QSpinBox {
                background: #faf8f5;
                border: 1px solid #d4c9bb;
                border-radius: 4px;
                padding: 3px 6px;
                color: #3d3229;
            }
            QLineEdit:focus, QComboBox:focus {
                border-color: #b8a48e;
            }
            QSpinBox, QDoubleSpinBox {
                background: #faf8f5;
                border: 1px solid #d4c9bb;
                border-radius: 4px;
                padding: 2px 6px;
                color: #3d3229;
            }
            QAbstractSpinBox::up-button, QAbstractSpinBox::down-button {
                background: #f7f3ee;
                border-left: 1px solid #d4c9bb;
                width: 14px;
            }
            QFrame#spinFrame {
                background: #faf8f5;
                border: 1px solid #d4c9bb;
                border-radius: 4px;
            }
            QFrame#spinFrame QDoubleSpinBox {
                background: transparent;
                border: none;
                padding: 2px 6px;
                color: #3d3229;
            }
            QToolButton#spinUpButton {
                background: #f7f3ee;
                border-left: 1px solid #d4c9bb;
                border-bottom: 1px solid #d4c9bb;
            }
            QToolButton#spinDownButton {
                background: #f7f3ee;
                border-left: 1px solid #d4c9bb;
            }
            QComboBox QAbstractItemView {
                background: #faf8f5;
                color: #3d3229;
                border: 1px solid #d4c9bb;
                selection-background-color: #e8ddd0;
                selection-color: #3d3229;
            }
            QAbstractItemView {
                background: #faf8f5;
                color: #3d3229;
                border: 1px solid #d4c9bb;
            }
            QAbstractItemView::item {
                background: #faf8f5;
                color: #3d3229;
            }
            QPushButton {
                color: #3d3229;
                border: 1px solid #d4c9bb;
                border-radius: 4px;
                padding: 4px 12px;
                background: #faf8f5;
            }
            QPushButton:hover {
                background: #ebe4da;
                border-color: #c4b6a4;
            }
            QPushButton:pressed {
                background: #ddd3c5;
            }
            QMenu {
                background: #faf8f5;
                border: 1px solid #ddd5ca;
                border-radius: 6px;
                padding: 4px 0;
            }
            QMenu::item {
                padding: 6px 24px 6px 12px;
                color: #3d3229;
            }
            QMenu::item:selected {
                background: #ebe4da;
                border-radius: 4px;
            }
            QMenu::separator {
                height: 1px;
                background: #ddd5ca;
                margin: 4px 8px;
            }
            QDialog, QMessageBox {
                background: #f4f0ea;
            }
            QDialog QLabel, QMessageBox QLabel {
                color: #3d3229;
            }
            QDialog QLineEdit, QMessageBox QLineEdit {
                background: #faf8f5;
                border: 1px solid #d4c9bb;
                border-radius: 4px;
                padding: 3px 6px;
                color: #3d3229;
            }
            QDialog QPushButton, QMessageBox QPushButton {
                background: #faf8f5;
                border: 1px solid #d4c9bb;
                border-radius: 4px;
                padding: 5px 14px;
                color: #3d3229;
            }
            QDialog QPushButton:hover, QMessageBox QPushButton:hover {
                background: #ebe4da;
            }
            QSlider::groove:horizontal {
                height: 6px;
                background: #ddd3c5;
                border-radius: 3px;
            }
            QSlider::handle:horizontal {
                width: 12px;
                height: 12px;
                background: #b8a48e;
                border-radius: 6px;
                margin: -4px 0;
            }
            QSlider::handle:horizontal:hover {
                background: #a6917a;
            }
            QStatusBar {
                background: #f7f3ee;
                border-top: 1px solid #ddd5ca;
                color: #7a6e61;
                padding: 2px 8px;
            }
            QStatusBar QLabel {
                color: #7a6e61;
            }
            """
        )

    def _update_zoom_label(self, zoom_percent: int) -> None:
        self._zoom_label.setText(f"{zoom_percent}%")

    def _open_arrow_settings(self) -> None:
        dialog = QDialog(self)
        dialog.setWindowTitle("Arrow Settings")
        dialog.setStyleSheet(self.styleSheet())
        layout = QVBoxLayout(dialog)

        preset_label = QLabel("Preset")
        preset_combo = QComboBox()
        preset_combo.addItems(["ACS", "Bold", "Fine"])
        preset_combo.currentTextChanged.connect(self._set_arrow_preset)

        width_label = QLabel("Width")
        width_slider = QSlider(Qt.Orientation.Horizontal)
        width_slider.setMinimum(1)
        width_slider.setMaximum(6)
        width_slider.setValue(int(self.canvas.get_arrow_line_width()))
        width_slider.valueChanged.connect(lambda value: self.canvas.set_arrow_line_width(value))

        head_label = QLabel("Head")
        head_slider = QSlider(Qt.Orientation.Horizontal)
        head_slider.setMinimum(10)
        head_slider.setMaximum(60)
        head_slider.setValue(int(self.canvas.get_arrow_head_scale() * 100))
        head_slider.valueChanged.connect(lambda value: self.canvas.set_arrow_head_scale(value / 100.0))

        snap_check = QCheckBox("Curve Snap")
        snap_check.setChecked(self.canvas.get_curved_snap())
        snap_check.toggled.connect(self.canvas.set_curved_snap)

        symmetry_check = QCheckBox("Curve Symmetry")
        symmetry_check.setChecked(self.canvas.get_curved_symmetry())
        symmetry_check.toggled.connect(self.canvas.set_curved_symmetry)

        snap_label = QLabel("Snap Step")
        snap_slider = QSlider(Qt.Orientation.Horizontal)
        snap_slider.setMinimum(5)
        snap_slider.setMaximum(40)
        snap_slider.setValue(int(self.canvas.get_curved_snap_step() * 100))
        snap_slider.valueChanged.connect(lambda value: self.canvas.set_curved_snap_step(value / 100.0))

        layout.addWidget(preset_label)
        layout.addWidget(preset_combo)
        layout.addWidget(width_label)
        layout.addWidget(width_slider)
        layout.addWidget(head_label)
        layout.addWidget(head_slider)
        layout.addWidget(snap_check)
        layout.addWidget(symmetry_check)
        layout.addWidget(snap_label)
        layout.addWidget(snap_slider)

        close_row = QHBoxLayout()
        close_row.addStretch(1)
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(dialog.accept)
        close_row.addWidget(close_btn)
        layout.addLayout(close_row)

        dialog.exec()

    def _template_entries(self) -> list[tuple[str, callable]]:
        return [
            ("Cyclopropane", lambda: self.canvas.begin_ring_template_insert(3)),
            ("Cyclobutane", lambda: self.canvas.begin_ring_template_insert(4)),
            ("Cyclopentane", lambda: self.canvas.begin_ring_template_insert(5)),
            ("Cyclohexane (Chair)", lambda: self.canvas.begin_ring_template_insert(6, style="chair")),
        ]

    def _acs_color_palette(self) -> list[tuple[str, str]]:
        return [
            ("Black", "#000000"),
            ("Gray", "#4a4a4a"),
            ("Red", "#c00000"),
            ("Blue", "#1f5eff"),
            ("Green", "#2e8b57"),
            ("Purple", "#6a2ea6"),
            ("Orange", "#c77c00"),
        ]

    def _apply_color_preset(self, hex_value: str) -> None:
        color = QColor(hex_value)
        tool = self.canvas.tools.tools.get("color") if hasattr(self.canvas, "tools") else None
        if tool is not None:
            tool._last_color = color.name()
        def apply_color() -> None:
            self.canvas.set_tool("color")
            for item in self.canvas.scene().selectedItems():
                if item.data(0) in {"bond", "atom", "ring"}:
                    self.canvas.apply_color_to_item(item, color)
        QTimer.singleShot(0, apply_color)

    def _apply_ring_fill_preset(self, hex_value: str) -> None:
        color = QColor(hex_value)
        def apply_fill() -> None:
            for item in self.canvas.scene().selectedItems():
                if item.data(0) == "ring":
                    self.canvas.apply_ring_fill_color(item, color)
        QTimer.singleShot(0, apply_fill)

    def _set_bond_style(self, value: str) -> None:
        mapping = {
            "Single": ("single", 1),
            "Double": ("double", 2),
            "Triple": ("triple", 3),
            "Bold": ("bold_in", 1),
            "Wedge": ("wedge", 1),
            "Hash": ("hash", 1),
        }
        style, order = mapping.get(value, ("single", 1))
        self.canvas.set_bond_style(style, order)

    _tool_display_names = {
        "select": "Select",
        "bond": "Bond",
        "text": "Atom / Text",
        "benzene": "Ring",
        "arrow": "Arrow",
        "ts_bracket": "TS Bracket",
        "orbital": "Orbital",
        "perspective": "Perspective",
        "color": "Color",
        "mark": "Mark",
    }

    def _sync_tool_actions_from_canvas(self) -> None:
        active = self.canvas.tools.active.name if self.canvas.tools.active is not None else None
        action = None
        if active == "bond":
            if self.canvas.active_bond_style in {"bold", "bold_in", "bold_out"}:
                action = self._tool_actions.get("bond_bold")
            elif self.canvas.active_bond_style == "wedge":
                action = self._tool_actions.get("bond_wedge")
            elif self.canvas.active_bond_style == "hash":
                action = self._tool_actions.get("bond_hash")
            else:
                action = self._tool_actions.get("bond")
        elif active == "mark":
            action = self._tool_actions.get(f"mark_{self.canvas.mark_kind}")
        elif active is not None:
            action = self._tool_actions.get(active)
        if action is not None:
            action.setChecked(True)

    def _set_tool_with_status(self, tool: str, reset_bond_style: bool = True) -> None:
        self.canvas.set_tool(tool)
        if tool == "bond" and reset_bond_style:
            self._set_bond_style("Single")
        display = self._tool_display_names.get(tool, tool.capitalize())
        self.statusBar().showMessage(f"{display} Tool")

    def _set_arrow_type(self, value: str) -> None:
        mapping = {
            "Reaction": "reaction",
            "Equilibrium": "equilibrium",
            "Resonance": "resonance",
            "Curved Single": "curved_single",
            "Curved Double": "curved_double",
            "Inhibition": "inhibit",
            "Dotted": "dotted",
        }
        self.canvas.set_arrow_type(mapping.get(value, "reaction"))

    def _set_orbital_type(self, value: str) -> None:
        mapping = {
            "s": "s",
            "p": "p",
            "sp": "sp",
            "sp2": "sp2",
            "sp3": "sp3",
            "d": "d",
            "MO bonding": "mo_bonding",
            "MO antibonding": "mo_antibonding",
        }
        self.canvas.set_orbital_type(mapping.get(value, "s"))

    def _set_orbital_phase(self, value: str) -> None:
        self.canvas.set_orbital_phase_enabled(value == "Phase On")

    def _set_arrow_preset(self, value: str) -> None:
        presets = {
            "ACS": (1.2, 0.3),
            "Bold": (2.2, 0.4),
            "Fine": (0.8, 0.25),
        }
        width, head = presets.get(value, (1.2, 0.3))
        self.canvas.set_arrow_line_width(width)
        self.canvas.set_arrow_head_scale(head)

    def _set_text_color(self) -> None:
        color = QColorDialog.getColor(parent=self, title="Text Color")
        if color.isValid():
            self.canvas.set_text_color(color)

    def _set_text_align(self, value: str) -> None:
        mapping = {"Left": "left", "Center": "center", "Right": "right"}
        self.canvas.set_text_alignment(mapping.get(value, "left"))

    def _set_note_box_color(self) -> None:
        color = QColorDialog.getColor(parent=self, title="Box Color")
        if color.isValid():
            self.canvas.set_note_box_color(color)

    def _set_note_border_color(self) -> None:
        color = QColorDialog.getColor(parent=self, title="Border Color")
        if color.isValid():
            self.canvas.set_note_border_color(color)

    def _set_text_preset(self, value: str) -> None:
        if value == "ACS":
            self.canvas.apply_text_preset_acs()
        elif value == "Paper Thin":
            self.canvas.apply_text_preset_paper_thin()
        elif value == "Paper Bold":
            self.canvas.apply_text_preset_paper_bold()

    def _save_canvas(self) -> None:
        path = resolve_save_path(current_path=self._current_file_path)
        if path is None:
            dialog_path, _ = QFileDialog.getSaveFileName(
                self,
                "Save Drawing",
                "",
                "LiteDraw (*.ldraw);;JSON (*.json);;All Files (*)",
            )
            path = resolve_save_path(dialog_path=dialog_path)
        if path is None:
            return
        try:
            self.canvas.save_to_file(path)
        except Exception as exc:
            QMessageBox.warning(self, "Save Error", f"Failed to save file:\n{exc}")
            return
        self._current_file_path = path
        self.statusBar().showMessage(f"Saved: {path}")

    def _load_canvas(self) -> None:
        dialog_path, _ = QFileDialog.getOpenFileName(
            self,
            "Load Drawing",
            "",
            "LiteDraw (*.ldraw);;JSON (*.json);;All Files (*)",
        )
        path = resolve_load_path(dialog_path)
        if path is None:
            return
        try:
            self.canvas.load_from_file(path)
        except Exception as exc:
            QMessageBox.warning(self, "Load Error", f"Failed to load file:\n{exc}")
            return
        self._current_file_path = path
        self.statusBar().showMessage(f"Loaded: {path}")

    def _set_bond_length(self) -> None:
        current = self.canvas.renderer.style.bond_length_px
        dialog = QDialog(self)
        dialog.setWindowTitle("Bond Length")
        dialog.setStyleSheet(self.styleSheet())
        layout = QVBoxLayout(dialog)

        label = QLabel("Set bond length (px):")
        layout.addWidget(label)

        frame = QFrame()
        frame.setObjectName("spinFrame")
        frame_layout = QHBoxLayout(frame)
        frame_layout.setContentsMargins(2, 2, 2, 2)
        frame_layout.setSpacing(0)

        spin = QDoubleSpinBox()
        spin.setDecimals(1)
        spin.setRange(10.0, 200.0)
        spin.setValue(current)
        spin.setButtonSymbols(QDoubleSpinBox.ButtonSymbols.NoButtons)
        spin.setMinimumWidth(90)
        spin.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        frame_layout.addWidget(spin)

        buttons_col = QVBoxLayout()
        buttons_col.setContentsMargins(0, 0, 0, 0)
        buttons_col.setSpacing(0)
        up_btn = ArrowButton("up")
        up_btn.setObjectName("spinUpButton")
        up_btn.setFixedSize(18, 14)
        down_btn = ArrowButton("down")
        down_btn.setObjectName("spinDownButton")
        down_btn.setFixedSize(18, 14)
        buttons_col.addWidget(up_btn)
        buttons_col.addWidget(down_btn)
        frame_layout.addLayout(buttons_col)

        layout.addWidget(frame)

        action_row = QHBoxLayout()
        action_row.addStretch(1)
        ok_btn = QPushButton("OK")
        cancel_btn = QPushButton("Cancel")
        action_row.addWidget(ok_btn)
        action_row.addWidget(cancel_btn)
        layout.addLayout(action_row)

        up_btn.clicked.connect(lambda: spin.setValue(min(200.0, spin.value() + 1.0)))
        down_btn.clicked.connect(lambda: spin.setValue(max(10.0, spin.value() - 1.0)))
        ok_btn.clicked.connect(dialog.accept)
        cancel_btn.clicked.connect(dialog.reject)

        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.canvas.set_bond_length(spin.value())
