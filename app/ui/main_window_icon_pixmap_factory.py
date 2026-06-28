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

    def _render_pixmap(self, painter_fn, size: int, dpr: float) -> QPixmap:
        # Render into a HiDPI-backed pixmap so the painter keeps working in
        # logical coordinates while the bitmap stays crisp on Retina.
        pixmap = QPixmap(round(size * dpr), round(size * dpr))
        pixmap.setDevicePixelRatio(dpr)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter_fn(painter)
        painter.end()
        return pixmap

    @staticmethod
    def _icon_from_pixmaps(pixmaps: list[QPixmap]) -> QIcon:
        icon = QIcon()
        for pixmap in pixmaps:
            for mode in (
                QIcon.Mode.Normal,
                QIcon.Mode.Active,
                QIcon.Mode.Selected,
                QIcon.Mode.Disabled,
            ):
                for state in (QIcon.State.Off, QIcon.State.On):
                    icon.addPixmap(pixmap, mode, state)
        return icon

    def make_icon(self, painter_fn, size: int | None = None) -> QIcon:
        size = self._default_size if size is None else size
        dpr = self._device_pixel_ratio()
        return self._icon_from_pixmaps([self._render_pixmap(painter_fn, size, dpr)])

    def make_sized_icon(self, sized_painter_fn: Callable[[QPainter, int], None], sizes) -> QIcon:
        """Build a single QIcon holding a crisp pixmap for each requested logical
        size, so small toolbars/option bars get an exact render instead of a
        downscale of one large bitmap. ``sized_painter_fn`` receives the painter
        and the logical size it should render at."""
        dpr = self._device_pixel_ratio()
        pixmaps = [
            self._render_pixmap(lambda painter, s=size: sized_painter_fn(painter, s), size, dpr) for size in sizes
        ]
        return self._icon_from_pixmaps(pixmaps)


__all__ = ["MainWindowIconPixmapFactory"]
