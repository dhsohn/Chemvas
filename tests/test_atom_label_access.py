import unittest
from types import SimpleNamespace

from chemvas.domain.document import Atom
from chemvas.ui.atom_label_access import (
    add_or_update_atom_label,
    atom_has_visible_label_for,
    clear_atom_label_for,
)
from chemvas.ui.canvas_atom_graphics_state import CanvasAtomGraphicsState
from tests.runtime_services import canvas_runtime_services
from tests.runtime_state import canvas_runtime_state


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
        self.wrapper_calls.append(
            (atom_id, text, clear_smiles, record, allow_merge, show_carbon)
        )


class AtomLabelAccessTest(unittest.TestCase):
    def test_lowercase_implicit_carbon_is_not_a_visible_label(self) -> None:
        canvas = SimpleNamespace(
            model=SimpleNamespace(
                atoms={
                    1: Atom("c", 0.0, 0.0),
                    2: Atom("c", 1.0, 0.0, explicit_label=True),
                }
            ),
            runtime_state=canvas_runtime_state(
                atom_graphics_state=CanvasAtomGraphicsState()
            ),
        )

        self.assertFalse(atom_has_visible_label_for(canvas, 1))
        self.assertTrue(atom_has_visible_label_for(canvas, 2))

    def test_add_or_update_atom_label_prefers_service_when_available(self) -> None:
        service_calls = []
        canvas = _FakeCanvas()
        canvas.services = canvas_runtime_services(
            atom_label_service=SimpleNamespace(
                add_or_update_atom_label=lambda atom_id, text, **kwargs: (
                    service_calls.append((atom_id, text, kwargs))
                )
            )
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

    def test_clear_atom_label_delegates_to_service_for_existing_atom(self) -> None:
        service_calls = []
        canvas = SimpleNamespace(
            model=SimpleNamespace(atoms={1: object()}),
            services=canvas_runtime_services(
                atom_label_service=SimpleNamespace(
                    add_or_update_atom_label=lambda atom_id, text, **kwargs: (
                        service_calls.append((atom_id, text, kwargs))
                    )
                )
            ),
        )

        clear_atom_label_for(canvas, 1)
        clear_atom_label_for(canvas, 99)

        self.assertEqual(service_calls, [(1, "C", {"show_carbon": False})])
