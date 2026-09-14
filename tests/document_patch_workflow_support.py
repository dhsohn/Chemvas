"""Public Graph Patch subprocess shared by desktop editing regressions."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys

from tests.subprocess_support import source_subprocess_env


def run_patch(tmp_path, source, operations):
    original = source.read_bytes()
    request = tmp_path / "request.json"
    request.write_text(
        json.dumps(
            {
                "format": "chemvas-graph-patch",
                "version": 1,
                "source_sha256": hashlib.sha256(original).hexdigest(),
                "operations": operations,
            }
        ),
        encoding="utf-8",
    )
    output = tmp_path / "patched.chemvas"
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "from chemvas.bootstrap.application import main; main()",
            "apply-patch",
            str(source),
            str(request),
            "--output",
            str(output),
        ],
        env=source_subprocess_env(
            {
                "PYTHONDONTWRITEBYTECODE": "1",
                "XDG_CONFIG_HOME": str(tmp_path / "config"),
                "XDG_DATA_HOME": str(tmp_path / "data"),
                "XDG_STATE_HOME": str(tmp_path / "state"),
            }
        ),
        capture_output=True,
        text=True,
        check=False,
        timeout=20,
    )
    assert source.read_bytes() == original
    return result, output
