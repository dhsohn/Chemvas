"""File > Export Figure's timeout, through the real child process and native export.

figure_svg runs the desktop's export in a child process with a time limit and
reports that no file was written when the limit passes. Here the real child
script runs unchanged except that, right after its native export has written
the figure, it records the file and then waits past the limit.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from chemvas.bootstrap import web_adapter

EXPORTED = 'service.export_figure(str(path), fmt="svg", scope=request["scope"])'


def test_figure_export_timeout_leaves_no_export_folder(tmp_path, monkeypatch):
    private = tmp_path / "private-tmp"
    private.mkdir()
    ready = tmp_path / "ready"
    # Both the server and its child keep their temporary files in `private`;
    # the marker sits outside it.
    monkeypatch.setattr(tempfile, "tempdir", str(private))
    for name in ("TMPDIR", "TEMP", "TMP"):
        monkeypatch.setenv(name, str(private))
    child = vars(web_adapter)["_FIGURE_EXPORT_CHILD"]
    assert child.count(EXPORTED) == 1
    monkeypatch.setattr(
        web_adapter,
        "_FIGURE_EXPORT_CHILD",
        child.replace(
            EXPORTED,
            EXPORTED + f'; __import__("pathlib").Path({str(ready)!r}).write_text('
            'f"{path}\\n{path.stat().st_size}", encoding="utf-8")'
            '; __import__("time").sleep(60)',
        ),
    )
    monkeypatch.setattr(web_adapter, "FIGURE_EXPORT_TIMEOUT_SECONDS", 5)
    document = web_adapter.edit_document(
        {
            "document": web_adapter.new_document(),
            "edit": {"kind": "ring", "x": 100, "y": 100},
        }
    )["document"]

    with pytest.raises(
        ValueError, match="The figure export took too long. No file was written."
    ):
        web_adapter.figure_svg(document, "sheet")

    # The native export wrote its figure in the private folder before the limit.
    assert ready.is_file()
    written, size = ready.read_text(encoding="utf-8").split("\n")
    assert private in Path(written).parents
    assert int(size) > 0
    # "No file was written" holds only if nothing of that export is left.
    assert sorted(str(path) for path in private.rglob("*")) == []
