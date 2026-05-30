import unittest
from types import SimpleNamespace

from ui.atom_label_access import add_or_update_atom_label


class _FakeCanvas:
    def __init__(self) -> None:
        self.wrapper_calls: list[tuple] = []

    def add_or_update_atom_label(
        self,
        atom_id: int,
        text: str,
        *,
        clear_smiles: bool = True,
        record: bool = True,
        allow_merge: bool = True,
        show_carbon: bool = False,
    ) -> None:
        self.wrapper_calls.append((atom_id, text, clear_smiles, record, allow_merge, show_carbon))


class AtomLabelAccessTest(unittest.TestCase):
    def test_add_or_update_atom_label_prefers_service_when_available(self) -> None:
        service_calls = []
        canvas = _FakeCanvas()
        canvas._atom_label_service = SimpleNamespace(
            add_or_update_atom_label=lambda atom_id, text, **kwargs: service_calls.append((atom_id, text, kwargs))
        )

        add_or_update_atom_label(
            canvas,
            4,
            "Cl",
            clear_smiles=False,
            record=False,
            allow_merge=False,
            show_carbon=True,
        )

        self.assertEqual(
            service_calls,
            [
                (
                    4,
                    "Cl",
                    {
                        "clear_smiles": False,
                        "record": False,
                        "allow_merge": False,
                        "show_carbon": True,
                    },
                )
            ],
        )
        self.assertEqual(canvas.wrapper_calls, [])

    def test_add_or_update_atom_label_requires_service(self) -> None:
        canvas = _FakeCanvas()

        with self.assertRaises(AttributeError):
            add_or_update_atom_label(canvas, 2, "N", record=False)


if __name__ == "__main__":
    unittest.main()
