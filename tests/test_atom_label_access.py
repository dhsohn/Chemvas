import sys
import unittest
from pathlib import Path
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[1]
APP_ROOT = ROOT / "app"
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

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

    def test_add_or_update_atom_label_falls_back_to_canvas_wrapper(self) -> None:
        canvas = _FakeCanvas()

        add_or_update_atom_label(canvas, 2, "N", record=False)

        self.assertEqual(canvas.wrapper_calls, [(2, "N", True, False, True, False)])


if __name__ == "__main__":
    unittest.main()
