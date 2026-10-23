"""Visual formatting must never change the text through legacy syntax."""

import pytest

from chemvas.features.annotations import (
    LabelRun,
    parse_arrow_label,
    serialize_arrow_label,
)


@pytest.mark.parametrize(
    ("runs", "expected"),
    [
        ([], ""),
        ([LabelRun("", "normal")], ""),
        (
            [LabelRun("H", "normal"), LabelRun("2", "sub"), LabelRun("O", "normal")],
            "H_{2}O",
        ),
        ([LabelRun("ΔG", "normal"), LabelRun("‡", "super")], "ΔG^{‡}"),
        ([LabelRun("{} \\ H₂O\nα", "normal")], "{} \\ H₂O\nα"),
        ([LabelRun("a", "normal"), LabelRun("", "sub"), LabelRun("b", "normal")], "ab"),
        ([LabelRun("2", "sub"), LabelRun("3", "sub")], "_{23}"),
        ([LabelRun("a\nb", "sub")], "_{a\nb}"),
        ([LabelRun("}", "super")], "^}"),
        ([LabelRun("a{b}", "sub"), LabelRun(" end", "normal")], "_{a{b}_} end"),
        ([LabelRun("_ ^", "normal")], "_ ^"),
        ([LabelRun("a} b", "sub")], "_{a}_}_{ b}"),
        ([LabelRun("a}^b", "super")], "^{a}^}^{^b}"),
        ([LabelRun("{}", "sub")], "_{{}_}"),
    ],
)
def test_encode_visual_runs(runs: list[LabelRun], expected: str) -> None:
    assert serialize_arrow_label(runs) == expected


@pytest.mark.parametrize(
    "runs",
    [
        [LabelRun("A_B", "normal")],
        [LabelRun("A^B", "normal")],
        [LabelRun("}", "sub"), LabelRun("B", "normal")],
        [LabelRun("text", "bold")],
    ],
)
def test_reject_unrepresentable_text_instead_of_corrupting_it(
    runs: list[LabelRun],
) -> None:
    with pytest.raises(
        ValueError, match="cannot be stored with the selected formatting"
    ):
        serialize_arrow_label(runs)


@pytest.mark.parametrize(
    "source",
    [
        "H_2",
        "K_{eq}",
        "A\\_B",
        "x_{a",
        "x_{}",
        "_ ^",
        "x^}",
        "x_{a{b}",
        "x^} y",
        "x_}^2",
        "_^2",
        "a\n_{b\nc}",
    ],
)
def test_existing_runs_reencode_without_changing_their_meaning(source: str) -> None:
    runs = parse_arrow_label(source)
    assert parse_arrow_label(serialize_arrow_label(runs)) == runs
