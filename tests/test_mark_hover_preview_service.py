import unittest
from types import SimpleNamespace
from unittest import mock

from chemvas.ui.canvas_hover_state import (
    HoverPreviewState,
    hover_preview_state_for,
    hover_state_for,
)
from chemvas.ui.mark_hover_preview_service import MarkHoverPreviewService
from PyQt6.QtCore import QPointF


def _mark_services(center: QPointF, item="item"):
    mark_scene_service = SimpleNamespace(
        mark_center_for_pointer=mock.Mock(return_value=center)
    )
    build_service = SimpleNamespace(
        build_mark_item=mock.Mock(return_value=item),
        set_mark_center=mock.Mock(),
    )
    return mark_scene_service, build_service


def _services(
    *,
    hover_scene_service=None,
    mark_scene_service=None,
    build_service=None,
):
    return SimpleNamespace(
        hover_scene_service=hover_scene_service,
        canvas_mark_scene_service=mark_scene_service,
        scene_decoration_build_service=build_service,
    )


def _service_for(canvas, *, find_atom_near):
    return MarkHoverPreviewService(
        canvas,
        hit_testing_service=SimpleNamespace(find_atom_near=find_atom_near),
        hover_scene_service=canvas.services.hover_scene_service,
    )


class MarkHoverPreviewServiceTest(unittest.TestCase):
    def test_add_mark_hover_preview_uses_injected_hover_scene_service(self) -> None:
        hover_scene_service = mock.Mock()
        find_atom_near = mock.Mock(return_value=1)
        mark_scene_service, build_service = _mark_services(QPointF(12.0, 18.0))
        canvas = SimpleNamespace(
            services=_services(
                hover_scene_service=hover_scene_service,
                mark_scene_service=mark_scene_service,
                build_service=build_service,
            ),
            renderer=SimpleNamespace(style=SimpleNamespace(bond_length_px=20.0)),
            mark_kind="plus",
            hover_preview_state=HoverPreviewState(),
        )

        _service_for(canvas, find_atom_near=find_atom_near).add_mark_hover_preview(
            QPointF(4.0, 5.0)
        )

        hover_scene_service.clear_hover_highlight.assert_called_once_with()
        hover_scene_service.add_atom_hover_indicator.assert_called_once_with(1)
        hover_scene_service.add_hover_preview_items.assert_called_once_with(["item"])
        build_service.set_mark_center.assert_called_once_with(
            "item", QPointF(12.0, 18.0)
        )

    def test_add_mark_hover_preview_adds_atom_preview_and_skips_duplicate_key(
        self,
    ) -> None:
        hover_scene_service = mock.Mock()
        find_atom_near = mock.Mock(return_value=1)
        mark_scene_service, build_service = _mark_services(QPointF(12.0, 18.0))
        canvas = SimpleNamespace(
            services=_services(
                hover_scene_service=hover_scene_service,
                mark_scene_service=mark_scene_service,
                build_service=build_service,
            ),
            renderer=SimpleNamespace(style=SimpleNamespace(bond_length_px=20.0)),
            mark_kind="plus",
            hover_preview_state=HoverPreviewState(),
        )
        service = _service_for(canvas, find_atom_near=find_atom_near)

        service.add_mark_hover_preview(QPointF(4.0, 5.0))

        self.assertEqual(hover_state_for(canvas).atom_id, 1)
        self.assertEqual(
            hover_preview_state_for(canvas).style, "mark:plus:atom:1:12.0:18.0"
        )
        hover_scene_service.clear_hover_highlight.assert_called_once_with()
        hover_scene_service.add_atom_hover_indicator.assert_called_once_with(1)
        build_service.set_mark_center.assert_called_once_with(
            "item", QPointF(12.0, 18.0)
        )
        hover_scene_service.add_hover_preview_items.assert_called_once_with(["item"])

        hover_scene_service.reset_mock()

        service.add_mark_hover_preview(QPointF(4.0, 5.0))

        hover_scene_service.assert_not_called()

    def test_add_mark_hover_preview_uses_injected_hit_testing_service(self) -> None:
        hover_scene_service = mock.Mock()
        hit_testing_service = SimpleNamespace(find_atom_near=mock.Mock(return_value=1))
        registry_hit_testing_service = SimpleNamespace(
            find_atom_near=mock.Mock(
                side_effect=AssertionError("registry service should not be used")
            )
        )
        mark_scene_service, build_service = _mark_services(QPointF(12.0, 18.0))
        services = _services(
            hover_scene_service=hover_scene_service,
            mark_scene_service=mark_scene_service,
            build_service=build_service,
        )
        services.hit_testing_service = registry_hit_testing_service
        canvas = SimpleNamespace(
            services=services,
            find_atom_near=mock.Mock(
                side_effect=AssertionError("canvas facade should not be used")
            ),
            renderer=SimpleNamespace(style=SimpleNamespace(bond_length_px=20.0)),
            mark_kind="plus",
            hover_preview_state=HoverPreviewState(),
        )

        MarkHoverPreviewService(
            canvas,
            hit_testing_service=hit_testing_service,
            hover_scene_service=hover_scene_service,
        ).add_mark_hover_preview(QPointF(4.0, 5.0))

        hit_testing_service.find_atom_near.assert_called_once_with(4.0, 5.0, 7.0)
        registry_hit_testing_service.find_atom_near.assert_not_called()
        canvas.find_atom_near.assert_not_called()
        self.assertEqual(hover_state_for(canvas).atom_id, 1)

    def test_add_mark_hover_preview_skips_duplicate_free_preview_and_handles_missing_item(
        self,
    ) -> None:
        hover_scene_service = mock.Mock()
        find_atom_near = mock.Mock(return_value=None)
        mark_scene_service, build_service = _mark_services(QPointF(3.5, 7.5))
        canvas = SimpleNamespace(
            services=_services(
                hover_scene_service=hover_scene_service,
                mark_scene_service=mark_scene_service,
                build_service=build_service,
            ),
            renderer=SimpleNamespace(style=SimpleNamespace(bond_length_px=20.0)),
            mark_kind="plus",
            hover_preview_state=HoverPreviewState("mark:plus:free:3.5:7.5"),
        )
        service = _service_for(canvas, find_atom_near=find_atom_near)

        service.add_mark_hover_preview(QPointF(3.5, 7.5))

        hover_scene_service.assert_not_called()

        hover_preview_state_for(canvas).style = None
        build_service.build_mark_item = mock.Mock(return_value=None)

        service.add_mark_hover_preview(QPointF(3.5, 7.5))

        hover_scene_service.clear_hover_highlight.assert_called_once_with()
        hover_scene_service.add_atom_hover_indicator.assert_not_called()
        hover_scene_service.add_hover_preview_items.assert_not_called()


if __name__ == "__main__":
    unittest.main()
