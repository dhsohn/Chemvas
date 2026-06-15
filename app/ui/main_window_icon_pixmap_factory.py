from __future__ import annotations

from collections.abc import Callable

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QGuiApplication, QIcon, QPainter, QPixmap


class MainWindowIconPixmapFactory:
    def __init__(
        self,
        *,
        default_size: int,
        device_pixel_ratio: Callable[[], float] | None = None,
    ) -> None:
        self._default_size = default_size
        self._device_pixel_ratio = self._screen_device_pixel_ratio if device_pixel_ratio is None else device_pixel_ratio

    @staticmethod
    def _screen_device_pixel_ratio() -> float:
        screen = QGuiApplication.primaryScreen()
        if screen is not None:
            return max(1.0, screen.devicePixelRatio())
        return 2.0

    def make_icon(self, painter_fn, size: int | None = None) -> QIcon:
        size = self._default_size if size is None else size
        # Render into a HiDPI-backed pixmap so the painter keeps working in
        # logical coordinates while the bitmap stays crisp on Retina.
        dpr = self._device_pixel_ratio()
        pixmap = QPixmap(round(size * dpr), round(size * dpr))
        pixmap.setDevicePixelRatio(dpr)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter_fn(painter)
        painter.end()
        icon = QIcon()
        for mode in (
            QIcon.Mode.Normal,
            QIcon.Mode.Active,
            QIcon.Mode.Selected,
            QIcon.Mode.Disabled,
        ):
            for state in (QIcon.State.Off, QIcon.State.On):
                icon.addPixmap(pixmap, mode, state)
        return icon


__all__ = ["MainWindowIconPixmapFactory"]
