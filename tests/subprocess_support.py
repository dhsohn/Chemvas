"""Environment for Python children that exercise this checkout's source."""

from __future__ import annotations

import os
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Mapping


def source_subprocess_env(
    overrides: Mapping[str, str] | None = None,
) -> dict[str, str]:
    environment = os.environ.copy()
    if overrides is not None:
        environment.update(overrides)
    app_root = Path(__file__).resolve().parents[1] / "app"
    ambient_path = environment.get("PYTHONPATH")
    environment["PYTHONPATH"] = os.pathsep.join(
        path for path in (str(app_root), ambient_path) if path
    )
    return environment
