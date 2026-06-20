import unittest

from core.document_state import validate_clipboard_selection_payload


def _valid_payload() -> dict:
    return {
        "format": "chemvas-selection",
        "version": 1,
        "atoms": [
            {"id": 0, "element": "C", "x": 1.0, "y": 2.0, "color": "#000000", "explicit_label": False},
            {"id": 1, "element": "O", "x": 3.0, "y": 4.0, "color": "#ff0000", "explicit_label": True},
        ],
        "bonds": [{"a": 0, "b": 1, "order": 2, "style": "double", "color": "#000000"}],
        "rings": [
            {
                "kind": "ring",
                "points": [[0.0, 0.0], [1.0, 0.0], [0.5, 1.0]],
                "atom_ids": [0, 1],
                "color": "#112233",
                "alpha": 0.3,
            }
        ],
        "marks": [
            {
                "kind": "mark",
                "mark_kind": "plus",
                "text": None,
                "atom_id": 0,
                "dx": 1.0,
                "dy": 1.0,
                "x": 2.0,
                "y": 3.0,
            }
        ],
        "scene_items": [
            {"kind": "note", "text": "hi", "x": 0.0, "y": 0.0},
            {"kind": "arrow", "start": [0, 0], "end": [1, 1], "control": None, "double": False},
            {"kind": "ts_bracket", "left": 0, "top": 0, "right": 1, "bottom": 1},
            {"kind": "orbital", "orbital_kind": "p", "center": [0, 0], "scale": 1.0, "rotation": 0.0},
        ],
    }


class ClipboardPayloadValidationTest(unittest.TestCase):
    def test_accepts_well_formed_payload(self) -> None:
        self.assertTrue(validate_clipboard_selection_payload(_valid_payload()))

    def test_accepts_empty_sections(self) -> None:
        payload = _valid_payload()
        payload["atoms"] = []
        payload["bonds"] = []
        payload["rings"] = []
        payload["marks"] = []
        payload["scene_items"] = []
        self.assertTrue(validate_clipboard_selection_payload(payload))

    def _assert_rejected(self, mutate) -> None:
        payload = _valid_payload()
        mutate(payload)
        self.assertFalse(validate_clipboard_selection_payload(payload))

    def test_rejects_non_string_element(self) -> None:
        self._assert_rejected(lambda p: p["atoms"][0].__setitem__("element", 6))

    def test_rejects_blank_element(self) -> None:
        self._assert_rejected(lambda p: p["atoms"][0].__setitem__("element", "   "))

    def test_rejects_non_finite_coordinate(self) -> None:
        self._assert_rejected(lambda p: p["atoms"][0].__setitem__("x", float("inf")))

    def test_rejects_bad_color(self) -> None:
        self._assert_rejected(lambda p: p["atoms"][0].__setitem__("color", "red"))

    def test_rejects_duplicate_atom_id(self) -> None:
        self._assert_rejected(lambda p: p["atoms"][1].__setitem__("id", 0))

    def test_rejects_extra_atom_key(self) -> None:
        self._assert_rejected(lambda p: p["atoms"][0].__setitem__("injected", 1))

    def test_rejects_invalid_bond_order(self) -> None:
        self._assert_rejected(lambda p: p["bonds"][0].__setitem__("order", 5))

    def test_rejects_invalid_bond_style(self) -> None:
        self._assert_rejected(lambda p: p["bonds"][0].__setitem__("style", "zigzag"))

    def test_rejects_bond_referencing_missing_atom(self) -> None:
        self._assert_rejected(lambda p: p["bonds"][0].__setitem__("b", 99))

    def test_rejects_ring_atom_outside_selection(self) -> None:
        self._assert_rejected(lambda p: p["rings"][0].__setitem__("atom_ids", [0, 42]))

    def test_rejects_invalid_mark_kind(self) -> None:
        self._assert_rejected(lambda p: p["marks"][0].__setitem__("mark_kind", "bogus"))

    def test_rejects_unknown_scene_item_kind(self) -> None:
        self._assert_rejected(lambda p: p["scene_items"].append({"kind": "wormhole"}))

    def test_rejects_arrow_without_endpoints(self) -> None:
        self._assert_rejected(lambda p: p["scene_items"][1].__setitem__("end", None))

    def test_rejects_invalid_orbital_kind(self) -> None:
        self._assert_rejected(lambda p: p["scene_items"][3].__setitem__("orbital_kind", "f"))

    def test_rejects_non_list_sections(self) -> None:
        self._assert_rejected(lambda p: p.__setitem__("atoms", {}))
        # Deepcopy isolation sanity: original template remains valid.
        self.assertTrue(validate_clipboard_selection_payload(_valid_payload()))


if __name__ == "__main__":
    unittest.main()
