from PyQt6.QtWidgets import QLabel, QVBoxLayout, QWidget


class Preview3D(QWidget):
    def __init__(self) -> None:
        super().__init__()
        layout = QVBoxLayout(self)
        placeholder = QLabel("3D preview placeholder")
        placeholder.setStyleSheet("color: #666;")
        layout.addWidget(placeholder)
