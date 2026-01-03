from PyQt6.QtCore import QPointF, QSize, Qt
from PyQt6.QtGui import (
    QAction,
    QActionGroup,
    QBrush,
    QColor,
    QFont,
    QIcon,
    QPainter,
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
    QLineEdit,
    QMainWindow,
    QMenu,
    QPushButton,
    QToolButton,
    QScrollArea,
    QSlider,
    QSpinBox,
    QTabWidget,
    QToolBar,
    QVBoxLayout,
    QWidget,
    QDialog,
    QDoubleSpinBox,
)

from ui.canvas_view import CanvasView


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
        painter.setBrush(QColor("#1f1f1f"))
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
        painter.setBrush(QColor("#1f1f1f"))
        rect = self.rect()
        size = 7
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

        self._init_toolbars()
        # Info controls moved to top bar; no dock panels needed.
        self._apply_theme()
        self.statusBar().showMessage("Ready")

    def _init_toolbars(self) -> None:
        tool_group = QActionGroup(self)
        tool_group.setExclusive(True)

        def tool_action(label: str, tool: str, shortcut: str | None = None) -> QAction:
            action = QAction(label, self)
            action.setCheckable(True)
            action.triggered.connect(lambda: self._set_tool_with_status(tool))
            if shortcut:
                action.setShortcut(shortcut)
            tool_group.addAction(action)
            return action

        left_bar = QToolBar("Tools", self)
        left_bar.setOrientation(Qt.Orientation.Vertical)
        left_bar.setMovable(False)
        left_bar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
        left_bar.setIconSize(QSize(20, 20))

        action_select = tool_action("Select", "select", "V")
        action_bond = tool_action("Bond", "bond", "B")
        action_text = tool_action("Atom", "text", "T")
        action_ring = tool_action("Ring", "benzene", "R")
        action_arrow = tool_action("Arrow", "arrow", "A")
        action_orbital = tool_action("Orbital", "orbital", "O")
        action_note = tool_action("Note", "note", "N")
        action_move = tool_action("Move", "move", "M")
        action_delete = tool_action("Erase", "delete", "X")
        action_color = tool_action("Color", "color", "C")
        action_perspective = tool_action("Perspective", "perspective")
        action_transform = tool_action("Transform", "transform")

        action_select.setIcon(self._icon_select())
        action_bond.setIcon(self._icon_bond())
        action_text.setIcon(self._icon_text())
        action_ring.setIcon(self._icon_ring())
        action_arrow.setIcon(self._icon_arrow())
        action_orbital.setIcon(self._icon_orbital())
        action_note.setIcon(self._icon_note())
        action_move.setIcon(self._icon_move())
        action_delete.setIcon(self._icon_erase())
        action_color.setIcon(self._icon_color())
        action_perspective.setIcon(self._icon_perspective())
        action_transform.setIcon(self._icon_transform())

        left_bar.addAction(action_select)
        left_bar.addAction(action_bond)
        left_bar.addAction(action_text)
        left_bar.addAction(action_ring)
        left_bar.addSeparator()
        arrow_button = CornerMenuButton()
        arrow_button.setDefaultAction(action_arrow)
        arrow_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        arrow_button.setStyleSheet(
            "QToolButton::menu-indicator { image: none; width: 0px; }"
            "QToolButton { padding-right: 2px; }"
        )
        arrow_menu = QMenu(arrow_button)
        for label in [
            "Reaction",
            "Equilibrium",
            "Resonance",
            "Curved Single",
            "Curved Double",
            "Inhibition",
            "Dotted",
        ]:
            action = arrow_menu.addAction(label)
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

        orbital_button = CornerMenuButton()
        orbital_button.setDefaultAction(action_orbital)
        orbital_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        orbital_button.setStyleSheet(
            "QToolButton::menu-indicator { image: none; width: 0px; }"
            "QToolButton { padding-right: 2px; }"
        )
        orbital_menu = QMenu(orbital_button)
        for label in ["s", "p", "sp", "sp2", "sp3", "d", "MO bonding", "MO antibonding"]:
            action = orbital_menu.addAction(label)
            action.triggered.connect(
                lambda checked=False, value=label: (
                    self._set_tool_with_status("orbital"),
                    self._set_orbital_type(value),
                )
            )
        orbital_menu.addSeparator()
        phase_action = orbital_menu.addAction("Phase On")
        phase_action.setCheckable(True)
        phase_action.setChecked(False)
        phase_action.toggled.connect(
            lambda checked: (
                self._set_tool_with_status("orbital"),
                self._set_orbital_phase("Phase On" if checked else "Phase Off"),
            )
        )
        orbital_button.setMenu(orbital_menu)

        left_bar.addWidget(arrow_button)
        left_bar.addWidget(orbital_button)
        left_bar.addAction(action_note)
        left_bar.addSeparator()
        left_bar.addAction(action_move)
        left_bar.addAction(action_delete)
        left_bar.addAction(action_color)
        left_bar.addAction(action_perspective)
        left_bar.addAction(action_transform)

        left_bar.addSeparator()

        bond_style_btn = CornerMenuButton()
        bond_style_btn.setToolTip("Bond Style")
        bond_style_btn.setIcon(self._icon_bond())
        bond_style_btn.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        bond_style_menu = QMenu(bond_style_btn)
        for label, icon in [
            ("Single", self._icon_bond()),
            ("Double", self._icon_bond_double()),
            ("Triple", self._icon_bond_triple()),
            ("Wedge", self._icon_bond_wedge()),
            ("Hash", self._icon_bond_hash()),
        ]:
            action = bond_style_menu.addAction(icon, label)
            action.triggered.connect(lambda checked=False, value=label: self._set_bond_style(value))
        bond_style_menu.triggered.connect(lambda action: bond_style_btn.setIcon(action.icon()))
        bond_style_btn.setMenu(bond_style_menu)
        bond_style_btn.setStyleSheet(
            "QToolButton::menu-indicator { image: none; width: 0px; }"
            "QToolButton { padding-right: 2px; }"
        )

        bond_len_btn = QToolButton()
        bond_len_btn.setToolTip("Bond Length")
        bond_len_btn.setIcon(self._icon_bond_length())
        bond_len_btn.clicked.connect(self._set_bond_length)

        flip_h = QToolButton()
        flip_h.setToolTip("Flip Horizontal")
        flip_h.setIcon(self._icon_flip_h())
        flip_h.clicked.connect(self.canvas.flip_horizontal)
        flip_v = QToolButton()
        flip_v.setToolTip("Flip Vertical")
        flip_v.setIcon(self._icon_flip_v())
        flip_v.clicked.connect(self.canvas.flip_vertical)

        left_bar.addWidget(bond_style_btn)
        left_bar.addWidget(bond_len_btn)
        left_bar.addWidget(flip_h)
        left_bar.addWidget(flip_v)

        self.addToolBar(Qt.ToolBarArea.LeftToolBarArea, left_bar)
        action_bond.setChecked(True)

        panel_bar = QToolBar("Panels", self)
        panel_bar.setMovable(False)
        panel_bar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
        panel_bar.setIconSize(QSize(22, 22))

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
        smiles_button.clicked.connect(lambda: self.canvas.load_smiles(smiles_input.text()))
        smiles_input.returnPressed.connect(lambda: self.canvas.load_smiles(smiles_input.text()))

        panel_bar.addWidget(undo_btn)
        panel_bar.addWidget(redo_btn)
        panel_bar.addSeparator()
        panel_bar.addWidget(smiles_input)
        panel_bar.addWidget(smiles_button)
        panel_bar.addSeparator()
        templates_button = CornerMenuButton()
        templates_button.setIcon(self._icon_templates())
        templates_button.setToolTip("Templates")
        templates_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        templates_button.setStyleSheet("QToolButton::menu-indicator { image: none; }")
        templates_menu = QMenu(templates_button)
        for label, handler in self._template_entries():
            templates_menu.addAction(label, handler)
        templates_button.setMenu(templates_menu)
        panel_bar.addWidget(templates_button)
        align_combo = QComboBox()
        align_combo.addItems(["Left", "Center", "Right"])
        align_combo.setToolTip("Info Alignment")
        align_combo.currentTextChanged.connect(self._set_info_align)

        insert_info = QToolButton()
        insert_info.setText("Insert Info")
        insert_info.clicked.connect(self.canvas.insert_info_label)

        format_input = QLineEdit()
        format_input.setPlaceholderText("{name_block} | {formula_block} | {mw_block}")
        format_input.setText(self.canvas.get_info_format())
        format_input.setFixedWidth(220)
        format_input.textChanged.connect(self._set_info_format)

        panel_bar.addWidget(align_combo)
        panel_bar.addWidget(insert_info)
        panel_bar.addWidget(format_input)

        panel_bar.addSeparator()

        atom_input = QLineEdit()
        atom_input.setPlaceholderText("Atom")
        atom_input.setFixedWidth(60)
        atom_input.setMaxLength(4)
        atom_input.setText(self.canvas.get_atom_symbol())
        atom_input.textChanged.connect(self.canvas.set_atom_symbol)
        panel_bar.addWidget(atom_input)
        panel_bar.addSeparator()

        text_size_frame = QFrame()
        text_size_frame.setObjectName("spinFrame")
        text_size_layout = QHBoxLayout(text_size_frame)
        text_size_layout.setContentsMargins(2, 2, 2, 2)
        text_size_layout.setSpacing(0)

        text_size = QSpinBox()
        text_size.setMinimum(6)
        text_size.setMaximum(48)
        text_size.setValue(self.canvas.get_text_size())
        text_size.valueChanged.connect(self.canvas.set_text_size)
        text_size.setToolTip("Text Size")
        text_size.setButtonSymbols(QSpinBox.ButtonSymbols.NoButtons)
        text_size.setMinimumWidth(50)
        text_size.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        text_size_layout.addWidget(text_size)

        text_buttons = QVBoxLayout()
        text_buttons.setContentsMargins(0, 0, 0, 0)
        text_buttons.setSpacing(0)
        text_up = ArrowButton("up")
        text_up.setObjectName("spinUpButton")
        text_up.setFixedSize(16, 12)
        text_down = ArrowButton("down")
        text_down.setObjectName("spinDownButton")
        text_down.setFixedSize(16, 12)
        text_up.clicked.connect(lambda: text_size.setValue(min(48, text_size.value() + 1)))
        text_down.clicked.connect(lambda: text_size.setValue(max(6, text_size.value() - 1)))
        text_buttons.addWidget(text_up)
        text_buttons.addWidget(text_down)
        text_size_layout.addLayout(text_buttons)

        text_bold = QToolButton()
        text_bold.setText("B")
        text_bold.setCheckable(True)
        text_bold.setChecked(self.canvas.get_text_weight() >= QFont.Weight.Bold)
        text_bold.setToolTip("Bold")
        text_bold.toggled.connect(
            lambda checked: self.canvas.set_text_weight(
                QFont.Weight.Bold if checked else QFont.Weight.Normal
            )
        )

        text_italic = QToolButton()
        text_italic.setText("I")
        text_italic.setCheckable(True)
        text_italic.setToolTip("Italic")
        text_italic.toggled.connect(self.canvas.set_text_italic)

        panel_bar.addWidget(text_size_frame)
        panel_bar.addWidget(text_bold)
        panel_bar.addWidget(text_italic)

        self.addToolBar(Qt.ToolBarArea.TopToolBarArea, panel_bar)

    def _make_icon(self, painter_fn) -> QIcon:
        pixmap = QPixmap(24, 24)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter_fn(painter)
        painter.end()
        return QIcon(pixmap)

    def _icon_select(self) -> QIcon:
        def draw(p):
            pen = QPen(Qt.GlobalColor.black)
            pen.setWidthF(1.4)
            p.setPen(pen)
            p.drawLine(5, 4, 5, 19)
            p.drawLine(5, 4, 14, 13)
            p.drawLine(5, 11, 11, 11)
        return self._make_icon(draw)

    def _icon_bond(self) -> QIcon:
        def draw(p):
            pen = QPen(Qt.GlobalColor.black)
            pen.setWidthF(1.8)
            p.setPen(pen)
            p.drawLine(4, 12, 20, 12)
        return self._make_icon(draw)

    def _icon_text(self) -> QIcon:
        def draw(p):
            font = QFont()
            font.setBold(True)
            font.setPointSize(10)
            p.setFont(font)
            p.setPen(QPen(Qt.GlobalColor.black))
            p.drawText(7, 16, "T")
        return self._make_icon(draw)

    def _icon_ring(self) -> QIcon:
        def draw(p):
            pen = QPen(Qt.GlobalColor.black)
            pen.setWidthF(1.4)
            p.setPen(pen)
            polygon = QPolygonF()
            polygon.append(QPointF(12, 4))
            polygon.append(QPointF(18, 8))
            polygon.append(QPointF(18, 16))
            polygon.append(QPointF(12, 20))
            polygon.append(QPointF(6, 16))
            polygon.append(QPointF(6, 8))
            p.drawPolygon(polygon)
        return self._make_icon(draw)

    def _icon_undo(self) -> QIcon:
        def draw(p):
            pen = QPen(Qt.GlobalColor.black)
            pen.setWidthF(1.4)
            p.setPen(pen)
            p.drawArc(4, 6, 14, 14, 90 * 16, 270 * 16)
            p.drawLine(6, 8, 4, 12)
            p.drawLine(6, 8, 9, 8)
        return self._make_icon(draw)

    def _icon_redo(self) -> QIcon:
        def draw(p):
            pen = QPen(Qt.GlobalColor.black)
            pen.setWidthF(1.4)
            p.setPen(pen)
            p.drawArc(6, 6, 14, 14, 180 * 16, 270 * 16)
            p.drawLine(18, 8, 20, 12)
            p.drawLine(18, 8, 15, 8)
        return self._make_icon(draw)

    def _icon_templates(self) -> QIcon:
        def draw(p):
            pen = QPen(Qt.GlobalColor.black)
            pen.setWidthF(1.0)
            p.setPen(pen)
            p.drawRect(5, 5, 6, 6)
            p.drawRect(13, 5, 6, 6)
            p.drawRect(5, 13, 6, 6)
            p.drawRect(13, 13, 6, 6)
        return self._make_icon(draw)

    def _icon_info(self) -> QIcon:
        def draw(p):
            pen = QPen(Qt.GlobalColor.black)
            pen.setWidthF(1.2)
            p.setPen(pen)
            p.drawEllipse(6, 6, 12, 12)
            p.drawLine(12, 10, 12, 15)
            p.drawPoint(12, 8)
        return self._make_icon(draw)

    def _icon_bond_double(self) -> QIcon:
        def draw(p):
            pen = QPen(Qt.GlobalColor.black)
            pen.setWidthF(1.4)
            p.setPen(pen)
            p.drawLine(4, 9, 20, 9)
            p.drawLine(4, 15, 20, 15)
        return self._make_icon(draw)

    def _icon_bond_triple(self) -> QIcon:
        def draw(p):
            pen = QPen(Qt.GlobalColor.black)
            pen.setWidthF(1.2)
            p.setPen(pen)
            p.drawLine(4, 8, 20, 8)
            p.drawLine(4, 12, 20, 12)
            p.drawLine(4, 16, 20, 16)
        return self._make_icon(draw)

    def _icon_bond_wedge(self) -> QIcon:
        def draw(p):
            p.setPen(QPen(Qt.GlobalColor.black))
            p.setBrush(QBrush(Qt.GlobalColor.black))
            polygon = QPolygonF([QPointF(5, 17), QPointF(19, 12), QPointF(5, 7)])
            p.drawPolygon(polygon)
        return self._make_icon(draw)

    def _icon_bond_hash(self) -> QIcon:
        def draw(p):
            pen = QPen(Qt.GlobalColor.black)
            pen.setWidthF(1.2)
            p.setPen(pen)
            for i, x in enumerate(range(6, 19, 3)):
                p.drawLine(x, 8 + i, x, 16 - i)
        return self._make_icon(draw)

    def _icon_bond_length(self) -> QIcon:
        def draw(p):
            pen = QPen(Qt.GlobalColor.black)
            pen.setWidthF(1.2)
            p.setPen(pen)
            p.drawLine(5, 12, 19, 12)
            p.drawLine(5, 9, 5, 15)
            p.drawLine(19, 9, 19, 15)
        return self._make_icon(draw)

    def _icon_flip_h(self) -> QIcon:
        def draw(p):
            pen = QPen(Qt.GlobalColor.black)
            pen.setWidthF(1.2)
            p.setPen(pen)
            p.drawLine(12, 4, 12, 20)
            p.drawLine(6, 7, 10, 7)
            p.drawLine(6, 17, 10, 17)
            p.drawLine(14, 7, 18, 7)
            p.drawLine(14, 17, 18, 17)
        return self._make_icon(draw)

    def _icon_flip_v(self) -> QIcon:
        def draw(p):
            pen = QPen(Qt.GlobalColor.black)
            pen.setWidthF(1.2)
            p.setPen(pen)
            p.drawLine(4, 12, 20, 12)
            p.drawLine(7, 6, 7, 10)
            p.drawLine(17, 6, 17, 10)
            p.drawLine(7, 14, 7, 18)
            p.drawLine(17, 14, 17, 18)
        return self._make_icon(draw)

    def _icon_arrow(self) -> QIcon:
        def draw(p):
            pen = QPen(Qt.GlobalColor.black)
            pen.setWidthF(1.6)
            p.setPen(pen)
            p.drawLine(4, 12, 18, 12)
            p.drawLine(18, 12, 14, 9)
            p.drawLine(18, 12, 14, 15)
        return self._make_icon(draw)

    def _icon_orbital(self) -> QIcon:
        def draw(p):
            pen = QPen(Qt.GlobalColor.black)
            pen.setWidthF(1.2)
            p.setPen(pen)
            p.drawEllipse(5, 8, 6, 8)
            p.drawEllipse(13, 8, 6, 8)
        return self._make_icon(draw)

    def _icon_note(self) -> QIcon:
        def draw(p):
            pen = QPen(Qt.GlobalColor.black)
            pen.setWidthF(1.2)
            p.setPen(pen)
            p.drawRect(5, 6, 14, 12)
            p.drawLine(7, 10, 17, 10)
            p.drawLine(7, 13, 15, 13)
        return self._make_icon(draw)

    def _icon_move(self) -> QIcon:
        def draw(p):
            pen = QPen(Qt.GlobalColor.black)
            pen.setWidthF(1.2)
            p.setPen(pen)
            p.drawLine(12, 4, 12, 20)
            p.drawLine(4, 12, 20, 12)
            p.drawLine(12, 4, 10, 6)
            p.drawLine(12, 4, 14, 6)
            p.drawLine(12, 20, 10, 18)
            p.drawLine(12, 20, 14, 18)
            p.drawLine(4, 12, 6, 10)
            p.drawLine(4, 12, 6, 14)
            p.drawLine(20, 12, 18, 10)
            p.drawLine(20, 12, 18, 14)
        return self._make_icon(draw)

    def _icon_erase(self) -> QIcon:
        def draw(p):
            pen = QPen(Qt.GlobalColor.black)
            pen.setWidthF(1.2)
            p.setPen(pen)
            p.setBrush(QBrush(Qt.GlobalColor.transparent))
            p.drawRect(6, 8, 12, 8)
            p.drawLine(8, 16, 16, 16)
        return self._make_icon(draw)

    def _icon_color(self) -> QIcon:
        def draw(p):
            pen = QPen(Qt.GlobalColor.black)
            pen.setWidthF(1.2)
            p.setPen(pen)
            p.drawEllipse(7, 7, 10, 10)
        return self._make_icon(draw)

    def _icon_transform(self) -> QIcon:
        def draw(p):
            pen = QPen(Qt.GlobalColor.black)
            pen.setWidthF(1.2)
            p.setPen(pen)
            p.drawRect(6, 6, 12, 12)
            p.drawEllipse(9, 9, 6, 6)
        return self._make_icon(draw)

    def _icon_perspective(self) -> QIcon:
        def draw(p):
            pen = QPen(Qt.GlobalColor.black)
            pen.setWidthF(1.2)
            p.setPen(pen)
            poly = QPolygonF(
                [
                    QPointF(6, 6),
                    QPointF(18, 8),
                    QPointF(16, 18),
                    QPointF(4, 16),
                ]
            )
            p.drawPolygon(poly)
        return self._make_icon(draw)

    def _init_panels(self) -> None:
        dock = QDockWidget("Panels", self)
        dock.setFeatures(QDockWidget.DockWidgetFeature.DockWidgetClosable)
        dock.setAllowedAreas(Qt.DockWidgetArea.LeftDockWidgetArea | Qt.DockWidgetArea.RightDockWidgetArea)
        dock.setMinimumWidth(260)
        dock.setMaximumWidth(360)

        tabs = QTabWidget()
        tabs.addTab(self._build_info_panel(), "Info")
        tabs.tabBar().hide()

        dock.setWidget(tabs)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, dock)
        self.panel_tabs = tabs
        self.panel_dock = dock

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
                background: #f3f3f3;
            }
            QToolBar {
                background: #f6f6f6;
                border: 1px solid #d6d6d6;
                spacing: 6px;
            }
            QToolButton {
                border: 1px solid transparent;
                border-radius: 4px;
                padding: 4px;
                color: #1f1f1f;
            }
            QToolButton:checked {
                background: #e3e7ee;
                border-color: #a9b7cc;
            }
            QLabel, QCheckBox, QGroupBox, QTabBar, QDockWidget, QToolButton {
                color: #1f1f1f;
            }
            QDockWidget {
                background: #f7f7f7;
                border: 1px solid #d6d6d6;
            }
            QTabWidget::pane {
                border: 1px solid #d6d6d6;
                background: #f9f9f9;
            }
            QTabBar::tab {
                background: #ececec;
                padding: 6px 10px;
                border: 1px solid #d6d6d6;
                border-bottom: none;
                margin-right: 2px;
                color: #1f1f1f;
            }
            QTabBar::tab:selected {
                background: #ffffff;
            }
            QLineEdit, QComboBox, QSpinBox {
                background: #ffffff;
                border: 1px solid #cfcfcf;
                padding: 3px 6px;
                color: #1f1f1f;
            }
            QSpinBox, QDoubleSpinBox {
                background: #fffaf7;
                border: 1px solid #cfcfcf;
                padding: 2px 6px;
                color: #1f1f1f;
            }
            QAbstractSpinBox::up-button, QAbstractSpinBox::down-button {
                background: #fffaf7;
                border-left: 1px solid #cfcfcf;
                width: 14px;
            }
            QFrame#spinFrame {
                background: #fffaf7;
                border: 1px solid #cfcfcf;
                border-radius: 4px;
            }
            QFrame#spinFrame QDoubleSpinBox {
                background: transparent;
                border: none;
                padding: 2px 6px;
                color: #1f1f1f;
            }
            QToolButton#spinUpButton {
                background: #fffaf7;
                border-left: 1px solid #cfcfcf;
                border-bottom: 1px solid #cfcfcf;
            }
            QToolButton#spinDownButton {
                background: #fffaf7;
                border-left: 1px solid #cfcfcf;
            }
            QComboBox QAbstractItemView {
                background: #ffffff;
                color: #1f1f1f;
                border: 1px solid #cfcfcf;
                selection-background-color: #e3e7ee;
                selection-color: #1f1f1f;
            }
            QAbstractItemView {
                background: #ffffff;
                color: #1f1f1f;
                border: 1px solid #cfcfcf;
            }
            QAbstractItemView::item {
                background: #ffffff;
                color: #1f1f1f;
            }
            QPushButton {
                color: #1f1f1f;
            }
            QDialog, QMessageBox {
                background: #f9f9f9;
            }
            QDialog QLabel, QMessageBox QLabel {
                color: #1f1f1f;
            }
            QDialog QLineEdit, QMessageBox QLineEdit {
                background: #ffffff;
                border: 1px solid #cfcfcf;
                padding: 3px 6px;
                color: #1f1f1f;
            }
            QDialog QPushButton, QMessageBox QPushButton {
                background: #ffffff;
                border: 1px solid #cfcfcf;
                padding: 4px 10px;
                color: #1f1f1f;
            }
            QSlider::groove:horizontal {
                height: 6px;
                background: #d9d9d9;
                border-radius: 3px;
            }
            QSlider::handle:horizontal {
                width: 10px;
                background: #8aa2c8;
                border-radius: 5px;
                margin: -4px 0;
            }
            """
        )

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
            ("Benzene", self.canvas.add_benzene_template),
            ("Cyclohexane Chair", self.canvas.add_cyclohexane_chair),
            ("Cyclopropane", self.canvas.add_cyclopropane),
            ("Cyclobutane", self.canvas.add_cyclobutane),
            ("Cyclopentane", self.canvas.add_cyclopentane),
            ("Naphthalene", self.canvas.add_naphthalene),
            ("Anthracene", self.canvas.add_anthracene),
            ("Phenanthrene", self.canvas.add_phenanthrene),
            ("Pyridine", self.canvas.add_pyridine),
            ("Pyrimidine", self.canvas.add_pyrimidine),
            ("Imidazole", self.canvas.add_imidazole),
            ("Pyrrole", self.canvas.add_pyrrole),
            ("Furan", self.canvas.add_furan),
            ("Thiophene", self.canvas.add_thiophene),
            ("Indole", self.canvas.add_indole),
            ("Quinoline", self.canvas.add_quinoline),
            ("Isoquinoline", self.canvas.add_isoquinoline),
            ("Benzimidazole", self.canvas.add_benzimidazole),
            ("Phenyl", self.canvas.add_phenyl),
            ("Benzyl", self.canvas.add_benzyl),
            ("Vinyl", self.canvas.add_vinyl),
            ("Allyl", self.canvas.add_allyl),
            ("Carboxyl", self.canvas.add_carboxyl),
            ("Nitro", self.canvas.add_nitro),
            ("Sulfonyl", self.canvas.add_sulfonyl),
            ("Carbonyl", self.canvas.add_carbonyl),
            ("t-Bu", self.canvas.add_tbu),
            ("i-Pr", self.canvas.add_ipr),
            ("Me", self.canvas.add_me),
            ("Et", self.canvas.add_et),
            ("Sugar (Pyranose)", self.canvas.add_pyranose),
            ("Sugar (Furanose)", self.canvas.add_furanose),
            ("Peptide (2-res)", self.canvas.add_peptide_2),
            ("12-crown-4", self.canvas.add_crown_12_4),
            ("15-crown-5", self.canvas.add_crown_15_5),
            ("18-crown-6", self.canvas.add_crown_18_6),
        ]

    def _build_info_panel(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)

        align_label = QLabel("Align")
        align_combo = QComboBox()
        align_combo.addItems(["Left", "Center", "Right"])
        align_combo.currentTextChanged.connect(self._set_info_align)

        insert_btn = QPushButton("Insert Info")
        insert_btn.clicked.connect(self.canvas.insert_info_label)

        format_label = QLabel("Format")
        format_input = QLineEdit()
        format_input.setPlaceholderText("{name_block} | {formula_block} | {mw_block}")
        format_input.setText(self.canvas.get_info_format())
        format_input.textChanged.connect(self._set_info_format)

        layout.addWidget(align_label)
        layout.addWidget(align_combo)
        layout.addWidget(insert_btn)
        layout.addWidget(format_label)
        layout.addWidget(format_input)
        return widget

    def _set_bond_style(self, value: str) -> None:
        mapping = {
            "Single": ("single", 1),
            "Double": ("double", 2),
            "Triple": ("triple", 3),
            "Wedge": ("wedge", 1),
            "Hash": ("hash", 1),
        }
        style, order = mapping.get(value, ("single", 1))
        self.canvas.set_bond_style(style, order)

    def _set_tool_with_status(self, tool: str) -> None:
        self.canvas.set_tool(tool)
        self.statusBar().showMessage(f"Tool: {tool}")

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

    def _set_info_align(self, value: str) -> None:
        mapping = {"Left": "left", "Center": "center", "Right": "right"}
        self.canvas.set_info_alignment(mapping.get(value, "left"))

    def _set_info_format(self, value: str) -> None:
        self.canvas.set_info_format(value)

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
