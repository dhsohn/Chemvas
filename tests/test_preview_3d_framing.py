from __future__ import annotations

import math

import pytest
from PyQt6.QtCore import QPoint, QPointF, QRectF, Qt
from PyQt6.QtGui import QColor, QFont, QImage, QPainter, QWheelEvent
from PyQt6.QtWidgets import QApplication

from chemvas.features.insertion import Molecule3DAtom, Molecule3DBond, Molecule3DScene
from chemvas.ui import preview_3d_painter
from chemvas.ui.preview_3d import Preview3D
from chemvas.ui.preview_3d_molecule_renderer import draw_projected_scene
from chemvas.ui.preview_3d_painter import (
    Preview3DPaintState,
    paint_preview_3d_panel,
    preview_layout_for_widget,
)
from chemvas.ui.preview_3d_projection import project_3d_scene


@pytest.fixture(scope="module")
def app():
    application = QApplication.instance() or QApplication([])
    application.setQuitOnLastWindowClosed(False)
    return application


def _scene(*, deep: bool = False) -> Molecule3DScene:
    x, y, z = (5.0, 4.0, 6.0) if deep else (1.0, 1.0, 0.0)
    return Molecule3DScene(
        atoms=(Molecule3DAtom("C", -x, -y, -z), Molecule3DAtom("O", x, y, z)),
        bonds=(Molecule3DBond(0, 1, 2),),
    )


def _pixel_bounds(image: QImage, rect: QRectF):
    dpr = image.devicePixelRatio()
    return (
        QRectF(rect.x() * dpr, rect.y() * dpr, rect.width() * dpr, rect.height() * dpr)
        .toAlignedRect()
        .intersected(image.rect())
    )


def _changed_pixels(before: QImage, after: QImage, rect: QRectF) -> int:
    assert before.size() == after.size()
    assert before.devicePixelRatio() == after.devicePixelRatio()
    bounds = _pixel_bounds(before, rect)
    return sum(
        before.pixel(x, y) != after.pixel(x, y)
        for y in range(bounds.top(), bounds.bottom() + 1)
        for x in range(bounds.left(), bounds.right() + 1)
    )


@pytest.mark.parametrize("size", [(560, 520), (260, 220), (1100, 220), (260, 900)])
def test_real_widget_wheel_keeps_header_footer_and_viewport_chrome_unchanged(
    app, size
) -> None:
    # Injecting an adapter disables background embedding; the actual widget,
    # wheel dispatch, layout, projection, molecule painter and grab remain real.
    preview = Preview3D(rdkit_adapter=object())
    preview.setFont(QFont("DejaVu Sans", 10))
    preview.resize(*size)
    scene = _scene()
    preview._scene = scene
    preview._formula_text = "CO"
    preview._mw_text = "28.01"
    preview._rotation_x = preview._rotation_y = 0.0
    try:
        preview.show()
        app.processEvents()
        before = preview.grab().toImage()
        assert (
            _changed_pixels(before, preview.grab().toImage(), QRectF(preview.rect()))
            == 0
        )
        for _ in range(14):
            event = QWheelEvent(
                QPointF(preview.rect().center()),
                QPointF(preview.mapToGlobal(preview.rect().center())),
                QPoint(),
                QPoint(0, 120),
                Qt.MouseButton.NoButton,
                Qt.KeyboardModifier.NoModifier,
                Qt.ScrollPhase.NoScrollPhase,
                False,
            )
            app.sendEvent(preview, event)
        app.processEvents()
        after = preview.grab().toImage()
        assert preview._zoom == 3.0
        assert preview._scene is scene
        layout = preview_layout_for_widget(
            QRectF(preview.rect()), ["FORMULA: CO", "MW: 28.01"], preview.font()
        )
        changed = {
            name: _changed_pixels(before, after, layout[name])
            for name in ("header", "footer", "molecule")
        }
        assert changed["molecule"] > 0, changed
        assert changed["header"] == changed["footer"] == 0, changed
        # Check every pixel outside the molecular content, including viewport
        # borders and interaction hints, not just two conveniently empty bands.
        molecule = _pixel_bounds(before, layout["molecule"])
        outside = sum(
            before.pixel(x, y) != after.pixel(x, y)
            for y in range(before.height())
            for x in range(before.width())
            if not molecule.contains(x, y)
        )
        assert outside == 0
    finally:
        preview.close()
        app.processEvents()


@pytest.mark.parametrize("size", [(484, 314), (200, 32), (900, 22), (36, 600)])
@pytest.mark.parametrize("angles", [(0, 0), (-18, 22), (67, 131), (180, 270)])
def test_initial_fit_includes_depth_magnified_discs_and_shadows(
    app, size, angles
) -> None:
    scene = _scene(deep=True)
    content = QRectF(38.0, 90.0, *size)
    projected = project_3d_scene(
        scene,
        rotation_x=math.radians(angles[0]),
        rotation_y=math.radians(angles[1]),
        zoom=1.0,
        content_rect=content,
    )
    assert len(projected) == len(scene.atoms)
    for x, y, _z, radius in projected:
        assert radius > 0
        # The existing renderer uses a 1.04-radius shadow at (+1.1, +1.8),
        # plus a one-pixel outline. Reserve another pixel for antialiasing.
        footprint = QRectF(
            x - radius * 1.04 - 1.0,
            y - radius * 1.04 - 1.0,
            radius * 2.08 + 3.1,
            radius * 2.08 + 3.8,
        )
        assert content.contains(footprint), (content, footprint, projected)
    # Also measure actual primitive paint, so clipping cannot conceal a failed
    # fit and a future bond/font/shadow change cannot silently invalidate it.
    images = []
    for clip in (False, True):
        image = QImage(
            size[0] + 80, size[1] + 180, QImage.Format.Format_ARGB32_Premultiplied
        )
        image.fill(QColor("white"))
        painter = QPainter(image)
        try:
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            if clip:
                painter.setClipRect(content)
            draw_projected_scene(painter, scene, projected)
        finally:
            painter.end()
        images.append(image)
    assert images[0] == images[1]
    assert any(
        images[0].pixelColor(x, y) != QColor("white")
        for y in range(int(content.top()), int(content.bottom()))
        for x in range(int(content.left()), int(content.right()))
    )


def test_user_zoom_is_applied_after_initial_fit_without_changing_depth_or_radii() -> (
    None
):
    scene = _scene(deep=True)
    content = QRectF(38.0, 90.0, 484.0, 314.0)
    center_x = content.center().x()
    center_y = content.top() + content.height() * 0.55
    results = {
        zoom: project_3d_scene(
            scene, rotation_x=0, rotation_y=0, zoom=zoom, content_rect=content
        )
        for zoom in (0.3, 1.0, 3.0)
    }
    for zoom in (0.3, 3.0):
        for fitted, changed in zip(results[1.0], results[zoom], strict=True):
            assert changed[0] - center_x == pytest.approx((fitted[0] - center_x) * zoom)
            assert changed[1] - center_y == pytest.approx((fitted[1] - center_y) * zoom)
            assert changed[2:] == fitted[2:]
    # User zoom remains meaningful: it may deliberately crop the molecule.
    assert any(not content.contains(QPointF(x, y)) for x, y, _z, _r in results[3.0])
    assert scene == _scene(deep=True)


def test_shallow_framing_is_unchanged_when_it_already_fits() -> None:
    scene = _scene()
    content = QRectF(38, 90, 484, 314)
    projected = project_3d_scene(
        scene, rotation_x=0, rotation_y=0, zoom=1, content_rect=content
    )
    scale = 314 * 0.36 / math.sqrt(2)
    assert projected == pytest.approx(
        [
            (content.center().x() - scale, content.top() + 314 * 0.55 + scale, 0, 9),
            (content.center().x() + scale, content.top() + 314 * 0.55 - scale, 0, 9),
        ]
    )


@pytest.mark.parametrize("size", [(484, 314), (200, 22)])
def test_single_atom_has_finite_centered_initial_fit(size) -> None:
    scene = Molecule3DScene((Molecule3DAtom("Cl", 20, -30, 700),), ())
    content = QRectF(38, 90, *size)
    [(x, y, z, radius)] = project_3d_scene(
        scene, rotation_x=3, rotation_y=-4, zoom=1, content_rect=content
    )
    assert x == content.center().x()
    assert y == content.top() + content.height() * 0.55
    assert z == 0
    assert 0 < radius <= 9
    assert content.contains(QRectF(x - radius, y - radius, radius * 2, radius * 2))


@pytest.mark.parametrize("content", [QRectF(), QRectF(10, 20, -10, 30)])
def test_empty_content_rect_has_no_projection(content) -> None:
    assert (
        project_3d_scene(
            _scene(), rotation_x=0, rotation_y=0, zoom=1, content_rect=content
        )
        == []
    )


@pytest.mark.parametrize("raise_during_molecule", [False, True])
def test_molecule_clip_intersects_and_restores_callers_clip_even_on_failure(
    app, monkeypatch, raise_during_molecule
) -> None:
    image = QImage(560, 520, QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(QColor("white"))
    painter = QPainter(image)
    original = QRectF(0, 0, 300, 520)
    painter.setClipRect(original)
    font = QFont("DejaVu Sans", 10)
    layout = preview_layout_for_widget(
        QRectF(image.rect()), ["FORMULA: CO", "MW: 28.01"], font
    )
    observed = []

    def molecule(painter, _scene, _projected):
        observed.append(painter.clipBoundingRect())
        painter.fillRect(QRectF(image.rect()), QColor("magenta"))
        if raise_during_molecule:
            raise RuntimeError("synthetic molecule paint failure")

    def hints(painter, _rect, **_kwargs):
        assert painter.clipBoundingRect() == original
        painter.fillRect(QRectF(10, 10, 5, 5), QColor("lime"))

    monkeypatch.setattr(preview_3d_painter, "draw_projected_scene", molecule)
    monkeypatch.setattr(preview_3d_painter, "draw_interaction_hints", hints)
    state = Preview3DPaintState(
        scene=_scene(),
        message="",
        formula_text="CO",
        mw_text="28.01",
        rotation_x=0,
        rotation_y=0,
        zoom=3,
    )
    try:
        if raise_during_molecule:
            with pytest.raises(RuntimeError, match="synthetic molecule paint failure"):
                paint_preview_3d_panel(painter, QRectF(image.rect()), font, state)
        else:
            paint_preview_3d_panel(painter, QRectF(image.rect()), font, state)
        assert observed == [original.intersected(layout["molecule"])]
        assert painter.clipBoundingRect() == original
    finally:
        painter.end()
    assert image.pixelColor(400, 200) == QColor("white")
    assert image.pixelColor(100, 200) == QColor("magenta")
    if not raise_during_molecule:
        assert image.pixelColor(12, 12) == QColor("lime")
