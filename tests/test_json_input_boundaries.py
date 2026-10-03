from __future__ import annotations

import json
from decimal import Decimal
from typing import TYPE_CHECKING

import pytest

from chemvas.domain.json_io import strict_json_loads

if TYPE_CHECKING:
    from collections.abc import Callable

# Escaped keys are spelled around chr(92) so the JSON escape itself, not a
# character Python already decoded, is what reaches the parser.
BACKSLASH = chr(92)
E_ACUTE = chr(0xE9)

EACH_REPRESENTATION = pytest.mark.parametrize(
    "as_input",
    [str, lambda text: text.encode("utf-8"), lambda text: bytearray(text, "utf-8")],
    ids=["str", "bytes", "bytearray"],
)


@EACH_REPRESENTATION
def test_strict_json_loads_accepts_each_input_representation(
    as_input: Callable[[str], str | bytes | bytearray],
) -> None:
    source = '{"name":"Ψ-é","items":[1,0.1,true,null]}'

    payload = strict_json_loads(as_input(source))

    # float 0.1 differs from Decimal("0.1"), so this also pins the number type.
    assert payload == {"name": "Ψ-é", "items": [1, Decimal("0.1"), True, None]}


@EACH_REPRESENTATION
@pytest.mark.parametrize(
    ("source", "key"),
    [
        (f'[{{"id":1}},{{"id":2,"{BACKSLASH}u0069d":3}}]', "id"),
        (f'{{"{BACKSLASH}u0069d":1,"id":2}}', "id"),
        (
            f'{{"rows":[{{"k{BACKSLASH}u00e9y":1,"k{E_ACUTE}y":2}}]}}',
            f"k{E_ACUTE}y",
        ),
        (f'[{{"{BACKSLASH}ud83e{BACKSLASH}uddea":1,"🧪":2}}]', "🧪"),
    ],
    ids=[
        "array-local",
        "escaped-ascii",
        "nested-escaped-non-ascii",
        "surrogate-pair",
    ],
)
def test_strict_json_loads_rejects_duplicate_decoded_keys(
    as_input: Callable[[str], str | bytes | bytearray], source: str, key: str
) -> None:
    assert BACKSLASH + "u" in source

    with pytest.raises(ValueError, match=f"duplicate JSON object key: {key}"):
        strict_json_loads(as_input(source))


@EACH_REPRESENTATION
@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ('[{"id":1},{"id":2}]', [{"id": 1}, {"id": 2}]),
        ('{"id":{"id":{"id":1}}}', {"id": {"id": {"id": 1}}}),
        # Precomposed and combining spellings are different keys; the parser
        # does not normalize them into a duplicate.
        (
            f'{{"{BACKSLASH}u00e9":1,"e{BACKSLASH}u0301":2}}',
            {E_ACUTE: 1, "e" + chr(0x301): 2},
        ),
    ],
    ids=["sibling-objects", "nested-levels", "unnormalized-unicode"],
)
def test_strict_json_loads_keeps_keys_unique_per_object_only(
    as_input: Callable[[str], str | bytes | bytearray], source: str, expected: object
) -> None:
    assert strict_json_loads(as_input(source)) == expected


@pytest.mark.parametrize(
    "number",
    [
        "0.1",
        "1.10",
        "-0.0",
        "1E+2",
        "1.5E-7",
        "12345678901234567890.123456789012345678901234567890",
    ],
)
def test_strict_json_loads_keeps_decimal_spelling_exact(number: str) -> None:
    value = strict_json_loads(number)

    assert type(value) is Decimal
    assert str(value) == number


def test_strict_json_loads_keeps_integers_and_literals_native() -> None:
    big = 123456789012345678901234567890

    payload = strict_json_loads(f"[7, -0, {big}, true, false, null]")

    assert payload == [7, 0, big, True, False, None]
    assert [type(item) for item in payload] == [int, int, int, bool, bool, type(None)]


@pytest.mark.parametrize(
    "source",
    [
        '{"a":1} {"b":2}',
        '{"a":1,}',
        '{"a":"line\nbreak"}',
        '{"a":01}',
        '{"a":.5}',
        '{"a":1.}',
        '{"a":+1}',
    ],
    ids=[
        "trailing-data",
        "trailing-comma",
        "raw-control-char",
        "leading-zero",
        "bare-fraction",
        "dangling-point",
        "plus-sign",
    ],
)
def test_strict_json_loads_rejects_malformed_text(source: str) -> None:
    with pytest.raises(json.JSONDecodeError):
        strict_json_loads(source)


@pytest.mark.parametrize("as_bytes", [bytes, bytearray])
@pytest.mark.parametrize(
    "codec",
    ["utf-16", "utf-16-le", "utf-16-be", "utf-32", "utf-32-le", "utf-32-be"],
)
def test_strict_json_loads_decodes_utf16_and_utf32_before_key_checks(
    codec: str, as_bytes: type[bytes] | type[bytearray]
) -> None:
    key = f"k{E_ACUTE}y"
    valid = as_bytes(f'{{"{key}":["Ψ",0.1]}}'.encode(codec))
    duplicate_text = f'{{"rows":[{{"k{BACKSLASH}u00e9y":1,"{key}":2}}]}}'
    duplicate = as_bytes(duplicate_text.encode(codec))

    # The plain codecs write a byte order mark in the host's byte order; the
    # -le/-be ones leave it out, so json.loads has to detect the encoding.
    boms = [bytes.fromhex(bom) for bom in ("fffe", "feff", "fffe0000", "0000feff")]
    assert valid.startswith(tuple(boms)) is (codec in ("utf-16", "utf-32"))
    assert BACKSLASH + "u00e9" in duplicate_text

    payload = strict_json_loads(valid)

    assert payload == {key: ["Ψ", Decimal("0.1")]}
    assert [type(item) for item in payload[key]] == [str, Decimal]

    with pytest.raises(ValueError) as excinfo:
        strict_json_loads(duplicate)

    assert str(excinfo.value) == f"duplicate JSON object key: {key}"
