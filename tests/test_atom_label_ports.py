from __future__ import annotations

from types import SimpleNamespace

from ui.atom_label_ports import atom_label_service_for_access


def test_atom_label_service_port_returns_attached_service() -> None:
    atom_label_service = object()
    canvas = SimpleNamespace(services=SimpleNamespace(atom_label_service=atom_label_service))

    assert atom_label_service_for_access(canvas) is atom_label_service
