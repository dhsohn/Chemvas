from __future__ import annotations

from unittest import mock

from PyQt6.QtCore import QPointF
from ui.structure_fragment_build_service import StructureFragmentBuildActions
from ui.structure_template_build_service import StructureTemplateBuildService


class _FakeFragmentBuilder:
    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple, dict]] = []

    def add_regular_ring_template(self, *args, **kwargs) -> None:
        self.calls.append(("add_regular_ring_template", args, kwargs))

    def add_hetero_ring_template(self, *args, **kwargs) -> None:
        self.calls.append(("add_hetero_ring_template", args, kwargs))

    def add_fused_heterocycle_template(self, *args, **kwargs) -> None:
        self.calls.append(("add_fused_heterocycle_template", args, kwargs))

    def add_phenyl(self, *args, **kwargs) -> None:
        self.calls.append(("add_phenyl", args, kwargs))


def _actions(*, run_recorded_build=None) -> StructureFragmentBuildActions:
    return StructureFragmentBuildActions(
        viewport_center=lambda: QPointF(1.0, 2.0),
        regular_ring_radius=lambda n: float(n),
        ring_points=lambda *args, **kwargs: [],
        cyclohexane_chair_points=lambda center: [],
        cyclohexane_boat_points=lambda center: [],
        add_ring_from_points=lambda *args, **kwargs: [],
        add_linear_chain=lambda *args, **kwargs: [],
        run_recorded_build=run_recorded_build or (lambda action: action()),
        latest_bond_id=lambda offset: offset,
    )


def test_template_build_service_passes_actions_to_fragment_builder() -> None:
    fragment_builder = _FakeFragmentBuilder()
    actions = _actions()
    service = StructureTemplateBuildService(fragment_builder, actions_factory=lambda: actions)

    service.add_regular_ring_template(6)
    service.add_hetero_ring_template(5, ["O", "C", "C", "C", "C"])
    service.add_phenyl()

    assert fragment_builder.calls == [
        ("add_regular_ring_template", (6, actions), {}),
        ("add_hetero_ring_template", (5, ["O", "C", "C", "C", "C"], actions), {}),
        ("add_phenyl", (actions,), {}),
    ]


def test_fused_heterocycle_templates_run_inside_recorded_build() -> None:
    fragment_builder = _FakeFragmentBuilder()
    run_recorded_build = mock.Mock(side_effect=lambda action: action())
    actions = _actions(run_recorded_build=run_recorded_build)
    service = StructureTemplateBuildService(fragment_builder, actions_factory=lambda: actions)

    service.add_indole()

    run_recorded_build.assert_called_once()
    assert fragment_builder.calls == [
        (
            "add_fused_heterocycle_template",
            (),
            {
                "ring_size": 5,
                "elements": ["N", "C", "C", "C", "C"],
                "x_scale": 1.1,
                "y_scale": 0.6,
                "actions": actions,
            },
        )
    ]


def test_direct_fused_heterocycle_template_can_use_explicit_actions() -> None:
    fragment_builder = _FakeFragmentBuilder()
    explicit_actions = _actions()
    service = StructureTemplateBuildService(
        fragment_builder,
        actions_factory=mock.Mock(side_effect=AssertionError("explicit actions should be used")),
    )

    service.add_fused_heterocycle_template(
        ring_size=6,
        elements=["N", "C", "C", "C", "C", "C"],
        x_scale=1.5,
        actions=explicit_actions,
    )

    assert fragment_builder.calls == [
        (
            "add_fused_heterocycle_template",
            (),
            {
                "ring_size": 6,
                "elements": ["N", "C", "C", "C", "C", "C"],
                "x_scale": 1.5,
                "y_scale": 0.0,
                "actions": explicit_actions,
            },
        )
    ]
