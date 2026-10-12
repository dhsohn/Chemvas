"""The common placement rule matches independent native/GDI observations."""

import json
from pathlib import Path

import pytest

from chemvas.features.annotations import atom_label_baseline_offset

ORACLE = json.loads(
    (Path(__file__).parent / "fixtures/native_label_baselines.json").read_text()
)


@pytest.mark.parametrize("case", ORACLE["cases"])
def test_native_baseline_uses_em_above_actual_descender(case):
    measured = atom_label_baseline_offset(case["em"], case["descent"])
    # Native CDXML rounds the independently measured p coordinates to 0.01 pt.
    assert measured == pytest.approx(case["baseline"], abs=0.0050001)
