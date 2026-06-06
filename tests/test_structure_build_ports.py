from __future__ import annotations

from types import SimpleNamespace

from ui.structure_build_ports import structure_build_service_for_access


def test_structure_build_service_port_returns_attached_service() -> None:
    build_service = object()
    canvas = SimpleNamespace(services=SimpleNamespace(structure_build_service=build_service))

    assert structure_build_service_for_access(canvas) is build_service
