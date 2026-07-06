import unittest

from core.document_state import (
    CLIPBOARD_SELECTION_PERSPECTIVE_VERSION,
    validate_clipboard_selection_payload,
)


def _valid_payload() -> dict:
    return {
        "format": "chemvas-selection",
        "version": 1,
        "atoms": [
            {"id": 0, "element": "C", "x": 1.0, "y": 2.0, "color": "#000000", "explicit_label": False},
            {"id": 1, "element": "O", "x": 3.0, "y": 4.0, "color": "#ff0000", "explicit_label": True},
            {"id": 2, "element": "C", "x": 2.0, "y": 5.0, "color": "#000000", "explicit_label": False},
        ],
        "bonds": [
            {"a": 0, "b": 1, "order": 2, "style": "double", "color": "#000000"},
            {"a": 1, "b": 2, "order": 1, "style": "single", "color": "#000000"},
            {"a": 2, "b": 0, "order": 1, "style": "single", "color": "#000000"},
        ],
        "rings": [
            {
                "kind": "ring",
                "points": [[1.0, 2.0], [3.0, 4.0], [2.0, 5.0]],
                "atom_ids": [0, 1, 2],
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

    def test_accepts_v2_perspective_state(self) -> None:
        payload = _valid_payload()
        payload["version"] = CLIPBOARD_SELECTION_PERSPECTIVE_VERSION
        payload["perspective"] = {
            "atom_coords_3d": [
                {"atom_id": 0, "coords": [1.0, 2.0, 3.0]},
                {"atom_id": 1, "coords": [4.0, 5.0, 6.0]},
            ],
            "projection_center_3d": [2.0, 3.0, 4.0],
            "projection_anchor_2d": [2.5, 3.5],
        }

        self.assertTrue(validate_clipboard_selection_payload(payload))

    def test_accepts_unattached_mark_without_offsets(self) -> None:
        payload = _valid_payload()
        payload["marks"] = [
            {
                "kind": "mark",
                "mark_kind": None,
                "text": None,
                "atom_id": None,
                "dx": None,
                "dy": None,
                "x": 2.0,
                "y": 3.0,
            }
        ]

        self.assertTrue(validate_clipboard_selection_payload(payload))

    def _assert_rejected(self, mutate) -> None:
        payload = _valid_payload()
        mutate(payload)
        self.assertFalse(validate_clipboard_selection_payload(payload))

    def test_rejects_top_level_extra_key(self) -> None:
        self._assert_rejected(lambda p: p.__setitem__("payload_json", "{}"))

    def test_rejects_string_numeric_atom_ids_and_references(self) -> None:
        cases = [
            ("atom id", lambda p: p["atoms"][0].__setitem__("id", "0")),
            ("bond endpoint a", lambda p: p["bonds"][0].__setitem__("a", "0")),
            ("bond endpoint b", lambda p: p["bonds"][0].__setitem__("b", "1")),
            ("ring atom id", lambda p: p["rings"][0].__setitem__("atom_ids", ["0", 1])),
            ("mark atom id", lambda p: p["marks"][0].__setitem__("atom_id", "0")),
        ]
        for name, mutate in cases:
            with self.subTest(name=name):
                self._assert_rejected(mutate)

    def test_rejects_invalid_perspective_state(self) -> None:
        def add_valid_perspective(payload: dict) -> None:
            payload["version"] = CLIPBOARD_SELECTION_PERSPECTIVE_VERSION
            payload["perspective"] = {
                "atom_coords_3d": [{"atom_id": 0, "coords": [1.0, 2.0, 3.0]}],
                "projection_center_3d": [2.0, 3.0, 4.0],
                "projection_anchor_2d": [2.5, 3.5],
            }

        def add_legacy_perspective(payload: dict) -> None:
            payload["perspective"] = {
                "atom_coords_3d": [{"atom_id": 0, "coords": [1.0, 2.0, 3.0]}],
                "projection_center_3d": None,
                "projection_anchor_2d": None,
            }

        def add_future_perspective(payload: dict) -> None:
            add_valid_perspective(payload)
            payload["version"] = CLIPBOARD_SELECTION_PERSPECTIVE_VERSION + 1

        def mutate_perspective(payload: dict, mutate) -> None:
            add_valid_perspective(payload)
            mutate(payload["perspective"])

        cases = [
            ("legacy version", add_legacy_perspective),
            ("future version", add_future_perspective),
            (
                "string atom id",
                lambda p: mutate_perspective(p, lambda state: state["atom_coords_3d"][0].__setitem__("atom_id", "0")),
            ),
            (
                "missing atom",
                lambda p: mutate_perspective(p, lambda state: state["atom_coords_3d"][0].__setitem__("atom_id", 99)),
            ),
            (
                "duplicate atom",
                lambda p: mutate_perspective(
                    p,
                    lambda state: state["atom_coords_3d"].append({"atom_id": 0, "coords": [4.0, 5.0, 6.0]}),
                ),
            ),
            (
                "bad coords",
                lambda p: mutate_perspective(p, lambda state: state["atom_coords_3d"][0].__setitem__("coords", [1.0, 2.0])),
            ),
            (
                "bad center",
                lambda p: mutate_perspective(p, lambda state: state.__setitem__("projection_center_3d", [1.0, 2.0])),
            ),
            ("extra key", lambda p: mutate_perspective(p, lambda state: state.__setitem__("extra", True))),
        ]
        for name, mutate in cases:
            with self.subTest(name=name):
                self._assert_rejected(mutate)

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

    def test_rejects_duplicate_bond_pairs(self) -> None:
        self._assert_rejected(
            lambda p: p["bonds"].append({"a": 1, "b": 0, "order": 1, "style": "single", "color": "#000000"})
        )

    def test_rejects_ring_atom_outside_selection(self) -> None:
        self._assert_rejected(lambda p: p["rings"][0].__setitem__("atom_ids", [0, 1, 42]))

    def test_rejects_degenerate_ring_points(self) -> None:
        self._assert_rejected(lambda p: p["rings"][0].__setitem__("points", [[0.0, 0.0], [1.0, 0.0]]))

    def test_rejects_degenerate_ring_atom_cycle(self) -> None:
        cases = [
            ("null", lambda p: p["rings"][0].__setitem__("atom_ids", None)),
            ("empty", lambda p: p["rings"][0].__setitem__("atom_ids", [])),
            ("short", lambda p: p["rings"][0].__setitem__("atom_ids", [0, 1])),
            ("duplicate", lambda p: p["rings"][0].__setitem__("atom_ids", [0, 1, 0])),
            ("missing closing bond", lambda p: p["bonds"].pop()),
            ("point count mismatch", lambda p: p["rings"][0]["points"].append([0.0, 0.5])),
            (
                "large coordinate mismatch",
                lambda p: (
                    p["atoms"][0].__setitem__("x", 1_000_000_000.0),
                    p["rings"][0]["points"][0].__setitem__(0, 1_000_000_000.5),
                ),
            ),
            (
                "huge integer coordinate mismatch",
                lambda p: (
                    p["atoms"][0].__setitem__("x", 10**20),
                    p["rings"][0]["points"][0].__setitem__(0, 10**20 + 1000),
                ),
            ),
            (
                "unrepresentable integer coordinate",
                lambda p: (
                    p["atoms"][0].__setitem__("x", 10**20 + 1),
                    p["rings"][0]["points"][0].__setitem__(0, 10**20 + 1),
                ),
            ),
            (
                "unsafe float coordinate",
                lambda p: (
                    p["atoms"][0].__setitem__("x", 1e20),
                    p["rings"][0]["points"][0].__setitem__(0, 1e20),
                ),
            ),
        ]
        for name, mutate in cases:
            with self.subTest(name=name):
                self._assert_rejected(mutate)

    def test_rejects_ring_alpha_out_of_range(self) -> None:
        self._assert_rejected(lambda p: p["rings"][0].__setitem__("alpha", 1.1))
        self._assert_rejected(lambda p: p["rings"][0].__setitem__("alpha", -0.1))

    def test_rejects_invalid_mark_kind(self) -> None:
        self._assert_rejected(lambda p: p["marks"][0].__setitem__("mark_kind", "bogus"))

    def test_rejects_mark_referencing_missing_atom(self) -> None:
        self._assert_rejected(lambda p: p["marks"][0].__setitem__("atom_id", 42))

    def test_rejects_unattached_mark_with_atom_offsets(self) -> None:
        self._assert_rejected(lambda p: p["marks"][0].update({"atom_id": None, "dx": 1.0, "dy": 1.0}))

    def test_rejects_mark_with_partial_offset(self) -> None:
        self._assert_rejected(lambda p: p["marks"][0].__setitem__("dy", None))

    def test_rejects_unknown_scene_item_kind(self) -> None:
        self._assert_rejected(lambda p: p["scene_items"].append({"kind": "wormhole"}))

    def test_rejects_arrow_without_endpoints(self) -> None:
        self._assert_rejected(lambda p: p["scene_items"][1].__setitem__("end", None))

    def test_rejects_arrow_extra_key_and_non_bool_double(self) -> None:
        self._assert_rejected(lambda p: p["scene_items"][1].__setitem__("injected", True))
        self._assert_rejected(lambda p: p["scene_items"][1].__setitem__("double", "yes"))

    def test_accepts_valid_shape_scene_item(self) -> None:
        payload = _valid_payload()
        payload["scene_items"].append(
            {
                "kind": "shape",
                "left": 0.0,
                "top": 1.0,
                "right": 2.0,
                "bottom": 3.0,
                "shape_kind": "rect",
                "stroke_style": "solid",
                "fill": "#123456",
                "fill_alpha": 0.4,
            }
        )

        self.assertTrue(validate_clipboard_selection_payload(payload))

    def test_rejects_shape_bad_fill_and_extra_keys(self) -> None:
        shape = {
            "kind": "shape",
            "left": 0.0,
            "top": 1.0,
            "right": 2.0,
            "bottom": 3.0,
            "shape_kind": "rect",
            "stroke_style": "solid",
        }
        self._assert_rejected(lambda p: p["scene_items"].append({**shape, "fill": "red"}))
        self._assert_rejected(lambda p: p["scene_items"].append({**shape, "fill": "#123456", "fill_alpha": 1.1}))
        self._assert_rejected(lambda p: p["scene_items"].append({**shape, "injected": True}))

    def test_rejects_invalid_orbital_kind(self) -> None:
        self._assert_rejected(lambda p: p["scene_items"][3].__setitem__("orbital_kind", "f"))

    def test_rejects_orbital_extra_key(self) -> None:
        self._assert_rejected(lambda p: p["scene_items"][3].__setitem__("injected", True))

    def test_rejects_non_list_sections(self) -> None:
        self._assert_rejected(lambda p: p.__setitem__("atoms", {}))
        # Deepcopy isolation sanity: original template remains valid.
        self.assertTrue(validate_clipboard_selection_payload(_valid_payload()))

    def test_rejects_unhashable_choice_values_without_type_error(self) -> None:
        # JSON arrays/objects where a string is expected must be rejected via
        # the normal False path, not crash the membership test with TypeError.
        self._assert_rejected(lambda p: p["bonds"][0].__setitem__("style", ["single"]))
        self._assert_rejected(lambda p: p["scene_items"][0].__setitem__("kind", ["note"]))
        self._assert_rejected(lambda p: p["marks"][0].__setitem__("mark_kind", {}))


if __name__ == "__main__":
    unittest.main()
