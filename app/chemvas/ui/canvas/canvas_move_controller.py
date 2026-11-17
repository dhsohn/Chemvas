from __future__ import annotations

from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, Any, Protocol

from chemvas.domain.document import VALID_ARROW_KINDS
from chemvas.domain.document.shapes import moved_shape
from chemvas.features.graph import geometry_bond_sets_for_atom_ids
from chemvas.features.selection import translate_projected_point_3d
from chemvas.ui.canvas.canvas_mark_registry import mark_registry_for
from chemvas.ui.canvas.canvas_ring_fill_scene_service import rebuild_ring_fill_polygons
from chemvas.ui.molecule.bond_renderer_access import update_bond_geometry_for

Coords3D = tuple[float, float, float]

# Annotation items whose geometry follows their Qt translation.
_MOVE_BY_ITEM_KINDS = frozenset(
    {
        "note",
    }
)


if TYPE_CHECKING:
    from collections.abc import Callable, Iterable, Mapping, MutableMapping, Sequence

    from chemvas.domain.document import MoleculeModel, Shape, TSBracket
    from chemvas.domain.points import PointLike
    from chemvas.ui.canvas.canvas_mark_registry import CanvasMarkRegistry
    from chemvas.ui.canvas.canvas_view import CanvasView


class SpatialIndexInvalidator(Protocol):
    """The one hit-testing operation a move needs: a stale-index flag."""

    def mark_spatial_index_dirty(self) -> object: ...


class ArrowRecords(Protocol):
    def record(self, item: Any) -> Any: ...
    def set_record(self, item: Any, record: Any) -> object: ...


@dataclass(frozen=True, kw_only=True)
class MovePorts:
    """What a move reads and refreshes, named instead of a canvas.

    ``for_canvas`` builds them from the desktop canvas, reading each at call
    time; tests pass their own so a move runs without a scene.
    """

    model: Callable[[], MoleculeModel]
    atom_bond_ids: Callable[[], MutableMapping[int, set[int]]]
    bond_items: Callable[[int], Iterable[Any]]
    update_bond_geometry: Callable[[int, bool], object]
    redraw_bond: Callable[[int], bool]
    redraw_connected_bonds: Callable[[int, int | None], object]
    ring_items: Callable[[], Sequence[Any]]
    update_ring_fills_for_atoms: Callable[[set[int]], object]
    update_selection_outline: Callable[[], object]
    # The resize/transform handles glued to an item, if it is the target.
    handles_for: Callable[[Any], Iterable[Any]]
    atom_label: Callable[[int], Any]
    atom_dot: Callable[[int], Any]
    position_label: Callable[[Any, float, float], object]
    marks: Callable[[], CanvasMarkRegistry]
    mark_center: Callable[[Any], PointLike]
    # The centre is the controller's point_factory point (QPointF by default).
    set_mark_center: Callable[[Any, Any], object]
    coords_3d: Callable[[], MutableMapping[int, Coords3D]]
    bond_length: Callable[[], float]
    projection_center_3d: Callable[[], Any]
    arrows: Callable[[], ArrowRecords]
    shape_record: Callable[[Any], Shape]
    set_shape_record: Callable[[Any, Shape], object]
    ts_bracket_record: Callable[[Any], TSBracket]
    set_ts_bracket_record: Callable[[Any, TSBracket], object]

    @classmethod
    def for_canvas(cls, canvas: CanvasView) -> MovePorts:
        runtime = lambda: canvas.runtime_state  # noqa: E731 - late-bound accessor
        services = lambda: canvas.services  # noqa: E731 - late-bound accessor

        def handles_for(item: Any) -> Iterable[Any]:
            handles = runtime().handle_state
            return handles.active_handles if item is handles.target else ()

        def shape_record(item: Any) -> Shape:
            from chemvas.ui.annotations.records import require_shape_record_for

            return require_shape_record_for(canvas, item)

        def set_shape_record(item: Any, shape: Shape) -> object:
            from chemvas.ui.annotations.records import set_shape_record_for

            return set_shape_record_for(canvas, item, shape)

        def ts_bracket_record(item: Any) -> TSBracket:
            from chemvas.ui.annotations.records import require_ts_bracket_record_for

            return require_ts_bracket_record_for(canvas, item)

        def set_ts_bracket_record(item: Any, bracket: TSBracket) -> object:
            from chemvas.ui.annotations.records import set_ts_bracket_record_for

            return set_ts_bracket_record_for(canvas, item, bracket)

        return cls(
            model=lambda: canvas.model,
            atom_bond_ids=lambda: runtime().graph_state.atom_bond_ids,
            bond_items=lambda bond_id: runtime().bond_graphics_state.bond_items.get(
                bond_id, []
            ),
            update_bond_geometry=lambda bond_id, rebuild: update_bond_geometry_for(
                canvas, bond_id, allow_topology_rebuild=rebuild
            ),
            redraw_bond=lambda bond_id: canvas.bond_renderer.redraw_bond(bond_id),
            redraw_connected_bonds=lambda atom_id, skip: (
                canvas.bond_renderer.redraw_connected_bonds(atom_id, skip_bond_id=skip)
            ),
            ring_items=lambda: runtime().ring_items(),
            update_ring_fills_for_atoms=lambda atom_ids: (
                services().canvas_ring_fill_scene_service.update_ring_fills_for_atoms(
                    atom_ids, ring_items=None
                )
            ),
            update_selection_outline=lambda: (
                services().selection.update_selection_outline()
            ),
            handles_for=handles_for,
            atom_label=lambda atom_id: runtime().atom_graphics_state.atom_items.get(
                atom_id
            ),
            atom_dot=lambda atom_id: runtime().atom_graphics_state.atom_dots.get(
                atom_id
            ),
            position_label=lambda label, x, y: (
                services().atom_label_service.position_label(label, x, y)
            ),
            marks=lambda: mark_registry_for(canvas),
            mark_center=lambda item: (
                services().scene_decoration_build_service.mark_center(item)
            ),
            set_mark_center=lambda item, center: (
                services().scene_decoration_build_service.set_mark_center(item, center)
            ),
            coords_3d=lambda: runtime().atom_coords_3d_state.atom_coords_3d,
            bond_length=lambda: canvas.renderer.style.bond_length_px,
            projection_center_3d=lambda: runtime().rotation_state.projection_center_3d,
            arrows=lambda: canvas.render_context.arrows,
            shape_record=shape_record,
            set_shape_record=set_shape_record,
            ts_bracket_record=ts_bracket_record,
            set_ts_bracket_record=set_ts_bracket_record,
        )


class CanvasMoveController:
    def __init__(
        self,
        ports: MovePorts,
        *,
        hit_testing_service: SpatialIndexInvalidator,
        ring_polygon_rebuilder=rebuild_ring_fill_polygons,
        point_factory=None,
    ) -> None:
        self.point_factory = point_factory
        self.ring_polygon_rebuilder = ring_polygon_rebuilder
        self.ports = ports
        self.marks = ports.marks()
        self.hit_testing_service = hit_testing_service

    @classmethod
    def for_canvas(cls, canvas: CanvasView, **kwargs: Any) -> CanvasMoveController:
        return cls(MovePorts.for_canvas(canvas), **kwargs)

    def move_item(
        self, item, dx: float, dy: float, update_selection: bool = True
    ) -> None:
        kind = item.data(0)
        if kind == "atom":
            atom_id = item.data(1)
            if not isinstance(atom_id, int):
                return
            if self.ports.model().atom_for_id(atom_id) is None:
                return
            # Delegate to move_atom so the atom's companions move together:
            # its label/dot, attached marks, 3D coordinates, and the hit-test
            # spatial index. The grabbed ``item`` is the registered label or
            # dot, which move_atom repositions by id, so we must not also call
            # item.moveBy here (that would double-move it). This mirrors the
            # multi-atom move_atoms path and fixes single-atom drags that
            # previously left marks behind and the spatial index stale.
            self.move_atom(atom_id, dx, dy)
            self.redraw_bonds_for_atoms({atom_id})
        elif kind == "bond":
            bond_id = item.data(1)
            if not isinstance(bond_id, int):
                return
            bond = self.ports.model().bond_for_id(bond_id)
            if bond is None:
                return
            self.move_atom(bond.a, dx, dy)
            self.move_atom(bond.b, dx, dy)
            self.redraw_bonds_for_atoms({bond.a, bond.b})
        elif kind == "mark":
            item.moveBy(dx, dy)
            data = item.data(1) or {}
            atom_id = data.get("atom_id")
            if isinstance(atom_id, int):
                atom = self.ports.model().atom_for_id(atom_id)
                if atom is not None:
                    center = self.ports.mark_center(item)
                    data["dx"] = center.x() - atom.x
                    data["dy"] = center.y() - atom.y
                    item.setData(1, data)
        elif kind == "shape":
            # Move a shape by rebuilding its path in scene coordinates and keeping
            # item.pos() at the origin. Using moveBy here would leave a non-zero
            # pos that a later resize (which rebuilds the path in scene space)
            # double-applies, making the shape jump away from its handles.
            shape = self.ports.shape_record(item)
            self.ports.set_shape_record(item, moved_shape(shape, dx, dy))
        elif kind == "ts_bracket":
            from chemvas.ui.annotations.records import moved_ts_bracket

            # Like a shape: the path is rebuilt in scene coordinates and
            # item.pos() stays at the origin.
            self.ports.set_ts_bracket_record(
                item, moved_ts_bracket(self.ports.ts_bracket_record(item), dx, dy)
            )
        elif kind in VALID_ARROW_KINDS:
            arrows = self.ports.arrows()
            record = arrows.record(item)
            arrows.set_record(
                item,
                replace(
                    record,
                    start=(record.start[0] + dx, record.start[1] + dy),
                    end=(record.end[0] + dx, record.end[1] + dy),
                    control=None
                    if record.control is None
                    else (record.control[0] + dx, record.control[1] + dy),
                ),
            )
        elif kind == "image":
            state = item.image_state()
            item.apply_image_state(
                {**state, "x": state["x"] + dx, "y": state["y"] + dy}
            )
        elif kind == "orbital":
            state = item.orbital_state()
            x, y = state["center"]
            item.apply_orbital_state({**state, "center": (x + dx, y + dy)})
        elif kind in _MOVE_BY_ITEM_KINDS:
            item.moveBy(dx, dy)
        self._shift_active_handles_for(item, dx, dy)
        if update_selection:
            self.ports.update_selection_outline()

    def _shift_active_handles_for(self, item, dx: float, dy: float) -> None:
        # Keep resize/transform handles glued to their item as it is dragged.
        for handle in self.ports.handles_for(item):
            handle.moveBy(dx, dy)

    def move_atoms(
        self,
        atom_ids: set[int],
        dx: float,
        dy: float,
        bond_ids: set[int] | None = None,
        redraw_bond_ids: set[int] | None = None,
        update_selection: bool = True,
        affected_ring_items: tuple[Any, ...] | None = None,
        rebuild_stale_bond_topology: bool = False,
    ) -> None:
        if not atom_ids:
            return
        for atom_id in atom_ids:
            self.move_atom(atom_id, dx, dy)
        use_bond_sets = bond_ids is not None or redraw_bond_ids is not None
        if use_bond_sets:
            _, dependent_ids = self.geometry_bond_sets_for_atom_ids(atom_ids)
            translated_ids = (bond_ids or set()) - dependent_ids
            refreshed_ids = (redraw_bond_ids or set()) | dependent_ids
            if translated_ids:
                for bond_id in translated_ids:
                    for item in self.ports.bond_items(bond_id):
                        item.moveBy(dx, dy)
            if refreshed_ids:
                for bond_id in refreshed_ids:
                    self.ports.update_bond_geometry(
                        bond_id, rebuild_stale_bond_topology
                    )
        else:
            self.redraw_bonds_for_atoms(atom_ids)
        if affected_ring_items is None:
            self.move_rings_for_atoms(atom_ids, dx, dy)
        else:
            self.move_rings_for_atoms(
                atom_ids,
                dx,
                dy,
                affected_ring_items=affected_ring_items,
            )
        if update_selection:
            self.ports.update_selection_outline()

    def redraw_bonds_for_atoms(self, atom_ids: set[int]) -> None:
        internal, dependent = self.geometry_bond_sets_for_atom_ids(atom_ids)
        for bond_id in internal | dependent:
            self.redraw_bond(bond_id)

    def update_bond_geometries_for_atoms(
        self, atom_ids: set[int], *, rebuild_stale_bond_topology: bool = False
    ) -> None:
        """Refresh coordinates in place when the graphics topology is unchanged.

        One-shot applications (history replay, gesture end) pass
        ``rebuild_stale_bond_topology=True`` so a bond whose length change
        altered its derived item count (hash marks) is rebuilt instead of
        keeping the frozen mid-gesture count.
        """

        internal, dependent = self.geometry_bond_sets_for_atom_ids(atom_ids)
        for bond_id in internal | dependent:
            self.ports.update_bond_geometry(bond_id, rebuild_stale_bond_topology)

    def redraw_bond(self, bond_id: int) -> bool:
        return self.ports.redraw_bond(bond_id)

    def redraw_connected_bonds(
        self, atom_id: int, skip_bond_id: int | None = None
    ) -> None:
        self.ports.redraw_connected_bonds(atom_id, skip_bond_id)

    def bond_ids_for_atom_ids(self, atom_ids: set[int]) -> set[int]:
        atom_bond_ids = self.ports.atom_bond_ids()
        bond_ids: set[int] = set()
        for atom_id in atom_ids:
            bond_ids.update(atom_bond_ids.get(atom_id, ()))
        return bond_ids

    def geometry_bond_sets_for_atom_ids(
        self, atom_ids: set[int]
    ) -> tuple[set[int], set[int]]:
        """Separate rigid translation from angle-dependent geometry refresh.

        A boundary edge changes direction relative to every edge at either end.
        Those edges include stationary neighbours and selected internal edges;
        neither may keep its previous outline or simply translate it. A whole
        connected selection still retains the rigid item-translation fast path.
        """
        model = self.ports.model()

        return geometry_bond_sets_for_atom_ids(
            atom_ids,
            self.ports.atom_bond_ids(),
            model.bonds,
            bond_for_id=model.bond_for_id,
        )

    def move_rings_for_atoms(
        self,
        atom_ids: set[int],
        _dx: float,
        _dy: float,
        *,
        affected_ring_items: tuple[Any, ...] | None = None,
    ) -> None:
        # A ring fill is a polygon over its atoms, so moving them refits it
        # rather than translating it; the deltas are the caller's, not ours.
        self.ring_polygon_rebuilder(
            self.ports.model(),
            atom_ids,
            self.ports.ring_items()
            if affected_ring_items is None
            else affected_ring_items,
        )

    def _set_atom_coordinates(
        self,
        atom_id: int,
        x: float,
        y: float,
        *,
        coords_3d: Coords3D | None = None,
    ) -> bool:
        """Apply screen coordinates and their depth-preserving or exact 3D value."""
        atom = self.ports.model().atom_for_id(atom_id)
        if atom is None:
            return False
        dx, dy = x - atom.x, y - atom.y
        atom.x, atom.y = x, y
        stored = self.ports.coords_3d()
        if coords_3d is not None:
            stored[atom_id] = coords_3d
        elif atom_id in stored:
            stored[atom_id] = translate_projected_point_3d(
                stored[atom_id],
                dx,
                dy,
                bond_length_px=self.ports.bond_length(),
                center_3d=self.ports.projection_center_3d(),
            )
        return True

    def _point_factory(self):
        point_factory = self.point_factory
        if point_factory is None:
            from PyQt6.QtCore import QPointF

            point_factory = QPointF
        return point_factory

    def _sync_atom_accessories(self, atom_id: int, x: float, y: float) -> None:
        """Relayout the label/dot and reattach marks from saved offsets."""
        label = self.ports.atom_label(atom_id)
        if label is not None:
            self.ports.position_label(label, x, y)
        dot = self.ports.atom_dot(atom_id)
        if dot is not None:
            dot.setPos(x, y)
        marks = self.marks.get_for_atom(atom_id)
        if not marks:
            return
        point_factory = self._point_factory()
        for mark in list(marks):
            data = mark.data(1) or {}
            dx, dy = data.get("dx"), data.get("dy")
            center = (
                point_factory(x + dx, y + dy)
                if isinstance(dx, (int, float)) and isinstance(dy, (int, float))
                else point_factory(x, y)
            )
            self.ports.set_mark_center(mark, center)

    def apply_atom_geometry(
        self,
        positions: Mapping[int, tuple[float, float]],
        *,
        coords_3d: Mapping[int, Coords3D | None] | None = None,
    ) -> set[int]:
        """Own absolute screen positions plus label/dot/mark and 3D cache sync.

        Missing ``coords_3d`` entries preserve depth through ordinary screen
        translation. Tuple entries install exactly. Explicit ``None`` removes
        the saved 3D entry. Cache-only mapping entries update the depth cache
        without moving screen items or accessories. Bond, ring, and selection
        refresh stay with the caller.
        """
        if not positions and not coords_3d:
            return set()
        # Invalidate before mutation so a partial accessory failure cannot leave
        # a still-clean index over drifted atom/mark geometry (matches the old
        # projected helper, which marked dirty first).
        self.hit_testing_service.mark_spatial_index_dirty()
        affected: set[int] = set()
        for atom_id, (x, y) in positions.items():
            atom = self.ports.model().atom_for_id(atom_id)
            if atom is None:
                continue
            if coords_3d is not None and atom_id in coords_3d:
                value = coords_3d[atom_id]
                if value is None:
                    atom.x, atom.y = x, y
                    self.ports.coords_3d().pop(atom_id, None)
                else:
                    self._set_atom_coordinates(atom_id, x, y, coords_3d=value)
            else:
                self._set_atom_coordinates(atom_id, x, y)
            affected.add(atom_id)
            self._sync_atom_accessories(atom_id, x, y)
        for atom_id, value in (coords_3d or {}).items():
            if atom_id in positions:
                continue
            if value is None:
                self.ports.coords_3d().pop(atom_id, None)
            else:
                self.ports.coords_3d()[atom_id] = value
            affected.add(atom_id)
        return affected

    def set_atom_positions(
        self,
        positions: dict[int, tuple[float, float]],
        *,
        update_selection: bool = True,
        coords_3d: dict[int, Coords3D] | None = None,
    ) -> None:
        """Apply absolute geometry for transforms and exact history restoration.

        Supplied 3D entries are restored exactly. Other moved atoms keep their
        depth and projection residual through the ordinary screen translation.
        Absolute application relayouts labels and reattaches marks by their
        saved offsets; pointer movement instead preserves current item offsets.
        """
        if not positions and not coords_3d:
            return
        # Keep nonexistent-atom filtering here: the shared owner stores
        # cache-only 3D for missing atoms (projection needs that), while this
        # one-shot path never installs depth for atoms absent from the model.
        owner_coords: dict[int, Coords3D] | None = None
        if coords_3d is not None:
            owner_coords = {
                atom_id: coord
                for atom_id, coord in coords_3d.items()
                if atom_id in positions
                or self.ports.model().atom_for_id(atom_id) is not None
            }
        atom_ids = self.apply_atom_geometry(positions, coords_3d=owner_coords)
        if atom_ids:
            self.update_bond_geometries_for_atoms(
                atom_ids, rebuild_stale_bond_topology=True
            )
            self.ports.update_ring_fills_for_atoms(atom_ids)
        if update_selection:
            self.ports.update_selection_outline()

    def move_atom(self, atom_id: int, dx: float, dy: float) -> None:
        atom = self.ports.model().atom_for_id(atom_id)
        if atom is None:
            return
        self._set_atom_coordinates(atom_id, atom.x + dx, atom.y + dy)
        self.hit_testing_service.mark_spatial_index_dirty()
        label = self.ports.atom_label(atom_id)
        if label is not None:
            label.moveBy(dx, dy)
        dot = self.ports.atom_dot(atom_id)
        if dot is not None:
            dot.moveBy(dx, dy)
        marks = self.marks.get_for_atom(atom_id)
        if marks:
            for mark in list(marks):
                mark.moveBy(dx, dy)


__all__ = ["CanvasMoveController", "MovePorts"]
