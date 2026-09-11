"""Machine reports remain UTF-8 even for POSIX surrogate-escaped paths."""

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from chemvas.bootstrap.document_cli_shared import json_text
from chemvas.core.document_io import write_document
from chemvas.domain.document import CANVAS_FILE_VERSION
from chemvas.features.document_composition import compose_document_state


@pytest.mark.parametrize("surrogate", ["\ud800", "\udce9", "\udfff"])
def test_json_report_escapes_surrogates_without_changing_unicode(surrogate):
    payload = {"path": f"반응-Å-{surrogate}.svg", "literal": r"\udce9", "emoji": "😀"}
    report = json_text(payload)
    encoded = report.encode("utf-8")
    assert json.loads(encoded) == payload
    assert "반응-Å-" in report
    assert "😀" in report
    assert surrogate not in report
    assert report.endswith("\n")


def test_surrogate_free_json_report_output_is_unchanged():
    payload = {"label": "반응 Å 😀", "path": r"literal-\udce9.svg", "nested": ["é", 3]}
    assert (
        json_text(payload)
        == json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    )


def _composition():
    return {
        "format": "chemvas-document-composition",
        "version": 1,
        "atoms": [{"id": 0, "element": "O", "x": 0, "y": 0}],
        "bonds": [],
        "notes": [{"text": "반응 Å", "x": 40, "y": 0}],
    }


def _byte_name(stem, suffix):
    return os.fsdecode(stem.encode("utf-8") + b"-\xe9." + suffix.encode("ascii"))


@pytest.mark.skipif(
    os.name != "posix", reason="POSIX byte filenames use surrogateescape"
)
@pytest.mark.parametrize("stdout_errors", ["surrogateescape", "strict"])
@pytest.mark.parametrize(
    "command", ["compose-document", "inspect-document", "render-document"]
)
def test_public_cli_byte_paths_emit_parseable_utf8_json(
    tmp_path, stdout_errors, command
):
    source = tmp_path / _byte_name("입력", "chemvas")
    write_document(source, compose_document_state(_composition()), CANVAS_FILE_VERSION)
    original = source.read_bytes()
    output = None
    request = None
    if command == "compose-document":
        request = tmp_path / _byte_name("요청", "json")
        request.write_text(
            json.dumps(_composition(), ensure_ascii=False), encoding="utf-8"
        )
        request_bytes = request.read_bytes()
        output = tmp_path / _byte_name("결과", "chemvas")
        args = [command, str(request), "--output", str(output)]
    elif command == "render-document":
        output = tmp_path / _byte_name("결과", "svg")
        args = [command, str(source), "--output", str(output)]
    else:
        args = [command, str(source)]
    environment = dict(
        os.environ,
        PYTHONPATH=str(Path(__file__).resolve().parents[1] / "app"),
        QT_QPA_PLATFORM="offscreen",
        PYTHONIOENCODING=f"utf-8:{stdout_errors}",
        XDG_DATA_HOME=str(tmp_path / "data"),
        XDG_CONFIG_HOME=str(tmp_path / "config"),
        XDG_CACHE_HOME=str(tmp_path / "cache"),
    )
    result = subprocess.run(
        [sys.executable, "-m", "chemvas", *args],
        capture_output=True,
        env=environment,
        timeout=20,
    )
    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout.decode("utf-8"))
    assert b"\\udce9" in result.stdout
    assert ("요청" if command == "compose-document" else "입력").encode(
        "utf-8"
    ) in result.stdout
    assert source.read_bytes() == original
    if request is not None:
        assert request.read_bytes() == request_bytes
        assert report["composition"] == str(request)
    else:
        assert report["source"] == str(source)
        assert report["source_sha256"] == hashlib.sha256(original).hexdigest()
    if output is not None:
        assert report["output"] == str(output)
        assert (
            report["output_sha256"] == hashlib.sha256(output.read_bytes()).hexdigest()
        )
        assert output.stat().st_size > 100
