from decimal import Decimal

import pytest
from chemvas.domain.json_io import strict_json_loads


def test_strict_json_loads_preserves_decimal_numbers() -> None:
    payload = strict_json_loads(b'{"value":1.25}')

    assert isinstance(payload, dict)
    assert isinstance(payload["value"], Decimal)
    assert payload["value"] == Decimal("1.25")


def test_strict_json_loads_rejects_nested_duplicate_keys() -> None:
    with pytest.raises(ValueError, match="duplicate JSON object key: value"):
        strict_json_loads(b'{"outer":{"value":1,"value":2}}')


@pytest.mark.parametrize("constant", ["NaN", "Infinity", "-Infinity"])
def test_strict_json_loads_rejects_nonstandard_numbers(constant: str) -> None:
    with pytest.raises(ValueError, match="non-standard JSON number"):
        strict_json_loads(f'{{"value":{constant}}}')
