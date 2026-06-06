from __future__ import annotations

from types import SimpleNamespace

from ui.handle_mutation_ports import (
    curved_arrow_path_service_for_access,
    handle_mutation_service_for_access,
)


def test_handle_mutation_ports_return_explicit_services() -> None:
    mutation_service = object()
    curved_path_service = object()
    canvas = SimpleNamespace(
        services=SimpleNamespace(
            handle_mutation_service=mutation_service,
            curved_arrow_path_service=curved_path_service,
        )
    )

    assert handle_mutation_service_for_access(canvas) is mutation_service
    assert curved_arrow_path_service_for_access(canvas) is curved_path_service
