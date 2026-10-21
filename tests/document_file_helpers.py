"""CDXML fixture creation through the production serializer."""

from pathlib import Path

from chemvas.bootstrap.document_cli_shared import encode_cli_document
from chemvas.core.document_io import atomic_write_via_temp, create_document
from chemvas.core.document_io import read_exact_snapshot as read_snapshot_exact
from chemvas.domain.document import MAX_DOCUMENT_BYTES
from chemvas.features.document_files import read_exact_document as read_cdxml_exact


def read_exact_document(path, **kwargs):
    return (read_snapshot_exact if Path(path).suffix == ".json" else read_cdxml_exact)(
        path, **kwargs
    )


def read_document(path):
    return read_exact_document(path).document


def write_document(path, state, version):
    if Path(path).suffix == ".json":
        from chemvas.core.document_io import write_snapshot

        return write_snapshot(path, state, version)
    document = create_document(state, version)
    raw = encode_cli_document(document.payload, max_bytes=MAX_DOCUMENT_BYTES)
    atomic_write_via_temp(path, lambda temporary: temporary.write_bytes(raw))
    return read_document(path)


__all__ = ["read_document", "read_exact_document", "write_document"]


def encode_payload(payload):
    """Build a CDXML metadata fixture, including intentionally invalid state."""
    import base64
    import hashlib
    import json

    native = (
        b'<?xml version="1.0"?><CDXML><page id="1" Width="842" Height="595"/></CDXML>'
    )
    encoded = base64.b64encode(json.dumps(payload, ensure_ascii=True).encode())
    return (
        native
        + b"\n<!-- ChemvasDocument:"
        + hashlib.sha256(native).hexdigest().encode()
        + b":"
        + encoded
        + b" -->\n"
    )


def read_payload(raw):
    """Inspect document fixture metadata without normalizing invalid test values."""
    import base64
    import json
    import re

    if isinstance(raw, str):
        raw = raw.encode()
    match = re.search(rb"<!-- ChemvasDocument:[0-9a-f]{64}:([A-Za-z0-9+/=]+) -->", raw)
    if match:
        return json.loads(base64.b64decode(match[1]))
    return json.loads(raw)


def write_payload_text(path, text, **kwargs):
    """Inject exact JSON state bytes into a CDXML fixture, without validation."""
    import base64
    import hashlib
    from pathlib import Path

    if Path(path).suffix.lower() != ".cdxml":
        return path.write_text(text, **kwargs)
    native = (
        b'<?xml version="1.0"?><CDXML><page id="1" Width="842" Height="595"/></CDXML>'
    )
    raw = (
        native
        + b"\n<!-- ChemvasDocument:"
        + hashlib.sha256(native).hexdigest().encode()
        + b":"
        + base64.b64encode(text.encode("utf-8"))
        + b" -->\n"
    )
    return path.write_bytes(raw)
