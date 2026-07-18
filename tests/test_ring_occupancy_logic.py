import unittest

from chemvas.domain.document import Bond
from chemvas.features.insertion import (
    point_inside_any_ring,
    ring_polygon_points_for_bond,
)
from PyQt6.QtCore import QPointF


class _FakePolygon:
    def __init__(
        self, points: list[tuple[float, float]], *, contains: bool = False
    ) -> None:
        self._points = [QPointF(x, y) for x, y in points]
        self._contains = contains

    def __iter__(self):
        return iter(self._points)

    def containsPoint(self, point: QPointF, fill_rule) -> bool:
        return self._contains


class _FakeRingItem:
    def __init__(self, atom_ids, polygon: _FakePolygon, *, crash: bool = False) -> None:
        self._atom_ids = atom_ids
        self._polygon = polygon
        self._crash = crash

    def data(self, key: int):
        if key == 2:
            return self._atom_ids
        return None

    def polygon(self) -> _FakePolygon:
        if self._crash:
            raise RuntimeError("deleted")
        return self._polygon


class RingOccupancyLogicTest(unittest.TestCase):
    def test_ring_polygon_points_for_bond_validates_and_returns_matching_polygon(
        self,
    ) -> None:
        bonds = [Bond(1, 2, 1), None]
        ring_items = [
            _FakeRingItem("not-a-list", _FakePolygon([(0.0, 0.0)])),
            _FakeRingItem([1, 3], _FakePolygon([(0.0, 0.0)])),
            _FakeRingItem(
                [1, 2, 3], _FakePolygon([(1.0, 2.0), (3.0, 4.0), (5.0, 6.0)])
            ),
        ]

        self.assertIsNone(
            ring_polygon_points_for_bond(-1, bonds=bonds, ring_items=ring_items)
        )
        self.assertIsNone(
            ring_polygon_points_for_bond(1, bonds=bonds, ring_items=ring_items)
        )
        self.assertEqual(
            ring_polygon_points_for_bond(0, bonds=bonds, ring_items=ring_items),
            [(1.0, 2.0), (3.0, 4.0), (5.0, 6.0)],
        )

    def test_ring_polygon_points_for_bond_skips_deleted_ring_items(self) -> None:
        bonds = [Bond(1, 2, 1)]
        ring_items = [
            _FakeRingItem([1, 2], _FakePolygon([(0.0, 0.0)]), crash=True),
            _FakeRingItem([1, 2, 3], _FakePolygon([(7.0, 8.0), (9.0, 10.0)])),
        ]

        self.assertEqual(
            ring_polygon_points_for_bond(0, bonds=bonds, ring_items=ring_items),
            [(7.0, 8.0), (9.0, 10.0)],
        )

    def test_point_inside_any_ring_uses_contains_and_skips_deleted_items(self) -> None:
        ring_items = [
            _FakeRingItem([1, 2], _FakePolygon([(0.0, 0.0)]), crash=True),
            _FakeRingItem([1, 2], _FakePolygon([(0.0, 0.0)], contains=False)),
            _FakeRingItem([2, 3], _FakePolygon([(1.0, 1.0)], contains=True)),
        ]

        self.assertTrue(point_inside_any_ring(QPointF(3.0, 4.0), ring_items=ring_items))
        self.assertFalse(
            point_inside_any_ring(
                QPointF(3.0, 4.0),
                ring_items=[
                    _FakeRingItem([1, 2], _FakePolygon([(0.0, 0.0)], contains=False))
                ],
            )
        )


if __name__ == "__main__":
    unittest.main()
