from __future__ import annotations

from types import SimpleNamespace
from unittest import mock

import pytest
from ui.structure_template_commands import (
    apply_structure_template_command,
    known_structure_template_keys,
)


def _template_service():
    method_names = (
        "add_regular_ring_template",
        "add_hetero_ring_template",
        "add_fused_benzenes",
        "add_crown_ether",
        "add_cyclohexane_chair",
        "add_phenyl",
    )
    template_builder = SimpleNamespace()
    service = SimpleNamespace(
        run_recorded_build=mock.Mock(side_effect=lambda action: action()),
        template_builder=template_builder,
    )
    for name in method_names:
        setattr(template_builder, name, mock.Mock())
    return service


def test_structure_template_commands_dispatch_recorded_catalog_templates() -> None:
    service = _template_service()

    apply_structure_template_command(service, "cyclopropane")
    apply_structure_template_command(service, "pyridine")
    apply_structure_template_command(service, "phenanthrene")
    apply_structure_template_command(service, "crown_18_6")

    assert service.run_recorded_build.call_count == 4
    service.template_builder.add_regular_ring_template.assert_called_once_with(3)
    service.template_builder.add_hetero_ring_template.assert_called_once_with(6, ["C", "C", "C", "C", "C", "N"])
    service.template_builder.add_fused_benzenes.assert_called_once_with(3, mode="angled")
    service.template_builder.add_crown_ether.assert_called_once_with(18, 6)


def test_structure_template_commands_dispatch_service_methods_and_unknown_keys() -> None:
    service = _template_service()

    apply_structure_template_command(service, "cyclohexane_chair")
    apply_structure_template_command(service, "phenyl")

    service.template_builder.add_cyclohexane_chair.assert_called_once_with()
    service.template_builder.add_phenyl.assert_called_once_with()
    assert "phenyl" in known_structure_template_keys()
    with pytest.raises(ValueError, match="Unknown structure template"):
        apply_structure_template_command(service, "not-a-template")
