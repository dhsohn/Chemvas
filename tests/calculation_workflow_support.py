"""Read the immutable historical document fixture for preservation tests."""

import json
from pathlib import Path

LEGACY_REVIEWED_PRECOMPLEX_FIXTURE = (
    Path(__file__).parent
    / "fixtures"
    / "document-v7"
    / "legacy-reviewed-precomplex.chemvas"
)


def _legacy_reviewed_precomplex_payload() -> dict[str, object]:
    """Return the v7 document whose plan stores a reviewed precomplex pair.

    Chemvas 0.15.0 wrote it through generate-precomplex and select-precomplex.
    Current releases no longer create or use that data but must keep reading and
    preserving it, so the file is a fixed witness and is never regenerated.
    """
    payload = json.loads(LEGACY_REVIEWED_PRECOMPLEX_FIXTURE.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    return payload
