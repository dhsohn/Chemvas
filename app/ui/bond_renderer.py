import math

from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtGui import QColor, QBrush, QPen, QPolygonF
from PyQt6.QtWidgets import QGraphicsLineItem, QGraphicsPolygonItem

from ui.graphics_items import NoSelectLineItem, NoSelectPolygonItem


class BondRenderer:
    def __init__(self, canvas) -> None:
        self.canvas = canvas
        self._bold_out_length_scale = 1.1

    @staticmethod
    def _reset_item_origin(item) -> None:
        if item is None:
            return
        pos = item.pos()
        if abs(pos.x()) <= 1e-6 and abs(pos.y()) <= 1e-6:
            return
        item.setPos(0.0, 0.0)

    @staticmethod
    def _normalize_3d(
        dx: float,
        dy: float,
        dz: float,
    ) -> tuple[float, float, float] | None:
        length = math.sqrt(dx * dx + dy * dy + dz * dz)
        if length <= 1e-9:
            return None
        return (dx / length, dy / length, dz / length)

    def _scale_segment(
        self,
        x1: float,
        y1: float,
        x2: float,
        y2: float,
        scale: float,
    ) -> tuple[float, float, float, float]:
        if scale <= 1.0 + 1e-6:
            return x1, y1, x2, y2
        dx = x2 - x1
        dy = y2 - y1
        extend = (scale - 1.0) * 0.5
        return (
            x1 - dx * extend,
            y1 - dy * extend,
            x2 + dx * extend,
            y2 + dy * extend,
        )

    def _extend_segment(
        self,
        x1: float,
        y1: float,
        x2: float,
        y2: float,
        extend: float,
    ) -> tuple[float, float, float, float]:
        if extend <= 1e-6:
            return x1, y1, x2, y2
        dx = x2 - x1
        dy = y2 - y1
        length = math.hypot(dx, dy) or 1.0
        factor = extend / length
        return (
            x1 - dx * factor,
            y1 - dy * factor,
            x2 + dx * factor,
            y2 + dy * factor,
        )

    def _bold_out_scale(self, bold_outward: bool, ring_center: QPointF | None) -> float:
        if bold_outward and ring_center is not None:
            return self._bold_out_length_scale
        return 1.0

    def _build_wedge_polygon(
        self,
        x1: float,
        y1: float,
        x2: float,
        y2: float,
        a_id: int | None = None,
        b_id: int | None = None,
    ) -> QPolygonF:
        dx = x2 - x1
        dy = y2 - y1
        length = math.hypot(dx, dy) or 1.0
        t0, t1 = self.canvas._trim_line_for_labels(a_id, b_id, x1, y1, x2, y2)
        base_x1 = x1 + dx * t0
        base_y1 = y1 + dy * t0
        base_x2 = x1 + dx * t1
        base_y2 = y1 + dy * t1
        dx = base_x2 - base_x1
        dy = base_y2 - base_y1
        base_x1 = base_x1 + dx * 0.1
        base_y1 = base_y1 + dy * 0.1
        dx = base_x2 - base_x1
        dy = base_y2 - base_y1
        length = math.hypot(dx, dy) or 1.0
        nx = -dy / length
        ny = dx / length
        half_width = self.canvas.renderer.bold_bond_pen().widthF() * 0.5 * 0.95
        p1 = QPointF(base_x1, base_y1)
        p2 = QPointF(base_x2 + nx * half_width, base_y2 + ny * half_width)
        p3 = QPointF(base_x2 - nx * half_width, base_y2 - ny * half_width)
        return QPolygonF([p1, p2, p3])

    def parallel_bond_segments(
        self,
        x1: float,
        y1: float,
        x2: float,
        y2: float,
        count: int,
        a_id: int | None = None,
        b_id: int | None = None,
    ) -> list[tuple[float, float, float, float]]:
        dx = x2 - x1
        dy = y2 - y1
        length = math.hypot(dx, dy) or 1.0
        offset_unit = None
        if a_id is not None and b_id is not None:
            offset_unit = self.canvas._bond_offset_unit_3d(a_id, b_id)
        if offset_unit is not None:
            nx, ny = offset_unit[0], offset_unit[1]
        else:
            nx = -dy / length
            ny = dx / length
        spacing = self.canvas.renderer.style.bond_spacing_px
        if count == 2:
            offsets = [-spacing / 2, spacing / 2]
        elif count == 3:
            offsets = [-spacing, 0.0, spacing]
        else:
            offsets = [0.0]
        t0, t1 = self.canvas._trim_line_for_labels(a_id, b_id, x1, y1, x2, y2)
        base_x1 = x1 + dx * t0
        base_y1 = y1 + dy * t0
        base_x2 = x1 + dx * t1
        base_y2 = y1 + dy * t1
        segments = []
        for offset in offsets:
            ox = nx * offset
            oy = ny * offset
            segments.append((base_x1 + ox, base_y1 + oy, base_x2 + ox, base_y2 + oy))
        return segments

    def wedge_polygon(
        self,
        x1: float,
        y1: float,
        x2: float,
        y2: float,
        a_id: int | None = None,
        b_id: int | None = None,
    ) -> QPolygonF:
        return self._build_wedge_polygon(x1, y1, x2, y2, a_id, b_id)

    def hash_segments(
        self,
        x1: float,
        y1: float,
        x2: float,
        y2: float,
        count: int,
        a_id: int | None = None,
        b_id: int | None = None,
    ) -> list[tuple[float, float, float, float]]:
        dx = x2 - x1
        dy = y2 - y1
        length = math.hypot(dx, dy) or 1.0
        t0, t1 = self.canvas._trim_line_for_labels(a_id, b_id, x1, y1, x2, y2)
        base_x1 = x1 + dx * t0
        base_y1 = y1 + dy * t0
        base_x2 = x1 + dx * t1
        base_y2 = y1 + dy * t1
        dx = base_x2 - base_x1
        dy = base_y2 - base_y1
        length = math.hypot(dx, dy) or 1.0
        nx = -dy / length
        ny = dx / length
        max_size = self.canvas.renderer.bold_bond_pen().widthF()
        if count <= 1:
            t_positions = [0.5]
            t_sizes = [1.0]
        else:
            t_positions = [i / (count - 1) for i in range(count)]
            t_sizes = [(i + 1) / (count + 1) for i in range(count)]
        max_t = max(t_sizes) if t_sizes else 1.0
        segments = []
        for t_pos, t_size in zip(t_positions, t_sizes):
            cx = base_x1 + dx * t_pos
            cy = base_y1 + dy * t_pos
            size = max_size * (t_size / max_t) if max_t > 0 else max_size
            hx = nx * size / 2.0
            hy = ny * size / 2.0
            segments.append((cx - hx, cy - hy, cx + hx, cy + hy))
        return segments

    def strip_polygon(
        self,
        x1: float,
        y1: float,
        x2: float,
        y2: float,
        nx: float,
        ny: float,
        base_width: float,
        bold_width: float,
    ) -> QPolygonF:
        half_base = base_width / 2.0
        inner_offset = half_base + max(0.0, bold_width - base_width)
        outer_offset = -half_base
        return QPolygonF(
            [
                QPointF(x1 + nx * outer_offset, y1 + ny * outer_offset),
                QPointF(x2 + nx * outer_offset, y2 + ny * outer_offset),
                QPointF(x2 + nx * inner_offset, y2 + ny * inner_offset),
                QPointF(x1 + nx * inner_offset, y1 + ny * inner_offset),
            ]
        )

    def ring_double_segments(
        self,
        a,
        b,
        center: QPointF,
        a_id: int | None = None,
        b_id: int | None = None,
        center_3d: tuple[float, float, float] | None = None,
    ) -> tuple[tuple[float, float, float, float], tuple[float, float, float, float], tuple[float, float]]:
        if center_3d is not None and a_id is not None and b_id is not None:
            coords_a = self.canvas._current_atom_coords_3d(a_id)
            coords_b = self.canvas._current_atom_coords_3d(b_id)
            if coords_a is not None and coords_b is not None:
                ax3, ay3, az3 = coords_a
                bx3, by3, bz3 = coords_b
                bond_vec3 = (bx3 - ax3, by3 - ay3, bz3 - az3)
                bond_unit3 = self._normalize_3d(*bond_vec3)
                if bond_unit3 is not None:
                    t0, t1 = self.canvas._trim_line_for_labels(a_id, b_id, a.x, a.y, b.x, b.y)
                    base_a3 = (
                        ax3 + bond_vec3[0] * t0,
                        ay3 + bond_vec3[1] * t0,
                        az3 + bond_vec3[2] * t0,
                    )
                    base_b3 = (
                        ax3 + bond_vec3[0] * t1,
                        ay3 + bond_vec3[1] * t1,
                        az3 + bond_vec3[2] * t1,
                    )
                    base_mid3 = (
                        (base_a3[0] + base_b3[0]) * 0.5,
                        (base_a3[1] + base_b3[1]) * 0.5,
                        (base_a3[2] + base_b3[2]) * 0.5,
                    )
                    inward3 = (
                        center_3d[0] - base_mid3[0],
                        center_3d[1] - base_mid3[1],
                        center_3d[2] - base_mid3[2],
                    )
                    dot = (
                        inward3[0] * bond_unit3[0]
                        + inward3[1] * bond_unit3[1]
                        + inward3[2] * bond_unit3[2]
                    )
                    inward_perp3 = (
                        inward3[0] - bond_unit3[0] * dot,
                        inward3[1] - bond_unit3[1] * dot,
                        inward3[2] - bond_unit3[2] * dot,
                    )
                    inward_unit3 = self._normalize_3d(*inward_perp3)
                    if inward_unit3 is not None:
                        outer_a = self.canvas._project_point_3d(base_a3)
                        outer_b = self.canvas._project_point_3d(base_b3)
                        base_outer = (outer_a[0], outer_a[1], outer_b[0], outer_b[1])
                        base_dx = base_outer[2] - base_outer[0]
                        base_dy = base_outer[3] - base_outer[1]
                        inner_length = math.hypot(base_dx, base_dy) or 1.0
                        has_label = False
                        if self.canvas._label_rect_for_atom(a_id) is not None:
                            has_label = True
                        if self.canvas._label_rect_for_atom(b_id) is not None:
                            has_label = True
                        if has_label:
                            inner_trim = max(0.6, inner_length * 0.08)
                        else:
                            inner_trim = max(1.0, inner_length * 0.12)
                        trim_ratio = min(0.45, inner_trim / inner_length)
                        trimmed_vec3 = (
                            base_b3[0] - base_a3[0],
                            base_b3[1] - base_a3[1],
                            base_b3[2] - base_a3[2],
                        )
                        spacing = self.canvas.renderer.style.bond_spacing_px * 1.1
                        inner_a3 = (
                            base_a3[0] + trimmed_vec3[0] * trim_ratio + inward_unit3[0] * spacing,
                            base_a3[1] + trimmed_vec3[1] * trim_ratio + inward_unit3[1] * spacing,
                            base_a3[2] + trimmed_vec3[2] * trim_ratio + inward_unit3[2] * spacing,
                        )
                        inner_b3 = (
                            base_b3[0] - trimmed_vec3[0] * trim_ratio + inward_unit3[0] * spacing,
                            base_b3[1] - trimmed_vec3[1] * trim_ratio + inward_unit3[1] * spacing,
                            base_b3[2] - trimmed_vec3[2] * trim_ratio + inward_unit3[2] * spacing,
                        )
                        inner_a = self.canvas._project_point_3d(inner_a3)
                        inner_b = self.canvas._project_point_3d(inner_b3)
                        offset_x = ((inner_a[0] + inner_b[0]) - (outer_a[0] + outer_b[0])) * 0.5
                        offset_y = ((inner_a[1] + inner_b[1]) - (outer_a[1] + outer_b[1])) * 0.5
                        offset_len = math.hypot(offset_x, offset_y)
                        if offset_len > 1e-9:
                            return (
                                base_outer,
                                (inner_a[0], inner_a[1], inner_b[0], inner_b[1]),
                                (offset_x / offset_len, offset_y / offset_len),
                            )

        dx = b.x - a.x
        dy = b.y - a.y
        length = math.hypot(dx, dy) or 1.0
        ux = dx / length
        uy = dy / length
        nx = -dy / length
        ny = dx / length
        offset_unit = None
        if a_id is not None and b_id is not None:
            offset_unit = self.canvas._bond_offset_unit_3d(
                a_id,
                b_id,
                target=center_3d,
            )
        if offset_unit is not None:
            nx, ny = offset_unit[0], offset_unit[1]
            if center_3d is None:
                mid_x = (a.x + b.x) / 2.0
                mid_y = (a.y + b.y) / 2.0
                to_cx = center.x() - mid_x
                to_cy = center.y() - mid_y
                if nx * to_cx + ny * to_cy < 0:
                    nx = -nx
                    ny = -ny
        else:
            mid_x = (a.x + b.x) / 2.0
            mid_y = (a.y + b.y) / 2.0
            to_cx = center.x() - mid_x
            to_cy = center.y() - mid_y
            if nx * to_cx + ny * to_cy < 0:
                nx = -nx
                ny = -ny

        spacing = self.canvas.renderer.style.bond_spacing_px * 1.1
        t0, t1 = self.canvas._trim_line_for_labels(a_id, b_id, a.x, a.y, b.x, b.y)
        base_bx1 = a.x + dx * t0
        base_by1 = a.y + dy * t0
        base_bx2 = a.x + dx * t1
        base_by2 = a.y + dy * t1

        inner_length = math.hypot(base_bx2 - base_bx1, base_by2 - base_by1) or 1.0
        has_label = False
        if a_id is not None and self.canvas._label_rect_for_atom(a_id) is not None:
            has_label = True
        if b_id is not None and self.canvas._label_rect_for_atom(b_id) is not None:
            has_label = True
        if has_label:
            inner_trim = max(0.6, inner_length * 0.08)
        else:
            inner_trim = max(1.0, inner_length * 0.12)
        inner_x1 = base_bx1 + ux * inner_trim + nx * spacing
        inner_y1 = base_by1 + uy * inner_trim + ny * spacing
        inner_x2 = base_bx2 - ux * inner_trim + nx * spacing
        inner_y2 = base_by2 - uy * inner_trim + ny * spacing
        return (base_bx1, base_by1, base_bx2, base_by2), (inner_x1, inner_y1, inner_x2, inner_y2), (nx, ny)

    def draw_ring_double_bond(
        self,
        a,
        b,
        center: QPointF,
        a_id: int | None = None,
        b_id: int | None = None,
        outer_style: str = "normal",
        center_3d: tuple[float, float, float] | None = None,
    ):
        outer_seg, inner_seg, (nx, ny) = self.ring_double_segments(
            a,
            b,
            center,
            a_id,
            b_id,
            center_3d=center_3d,
        )
        if outer_style in {"bold_inward", "bold_outward"}:
            use_nx, use_ny = (nx, ny) if outer_style == "bold_inward" else (-nx, -ny)
            outer_item = self.one_sided_bond_strip(
                *outer_seg,
                use_nx,
                use_ny,
                self.canvas.renderer.style.bond_line_width,
                self.canvas.renderer.style.bold_bond_width * 1.5,
            )
        else:
            outer_item = NoSelectLineItem(*outer_seg)
            outer_item.setPen(self.canvas.renderer.bond_pen())
        inner_line = NoSelectLineItem(*inner_seg)
        inner_line.setPen(self.canvas.renderer.bond_pen())
        return [outer_item, inner_line]

    def one_sided_bond_strip(
        self,
        x1: float,
        y1: float,
        x2: float,
        y2: float,
        nx: float,
        ny: float,
        base_width: float,
        bold_width: float,
    ):
        if bold_width <= base_width + 1e-6:
            line_item = NoSelectLineItem(x1, y1, x2, y2)
            line_item.setPen(self.canvas.renderer.bond_pen())
            return line_item
        half_base = base_width / 2.0
        inner_offset = half_base + max(0.0, bold_width - base_width)
        outer_offset = -half_base
        polygon = QPolygonF(
            [
                QPointF(x1 + nx * outer_offset, y1 + ny * outer_offset),
                QPointF(x2 + nx * outer_offset, y2 + ny * outer_offset),
                QPointF(x2 + nx * inner_offset, y2 + ny * inner_offset),
                QPointF(x1 + nx * inner_offset, y1 + ny * inner_offset),
            ]
        )
        item = NoSelectPolygonItem(polygon)
        item.setPen(QPen(Qt.PenStyle.NoPen))
        item.setBrush(QBrush(QColor(self.canvas.renderer.style.bond_color)))
        return item

    def draw_parallel_bonds(
        self,
        x1: float,
        y1: float,
        x2: float,
        y2: float,
        count: int,
        a_id: int | None = None,
        b_id: int | None = None,
    ):
        dx = x2 - x1
        dy = y2 - y1
        length = math.hypot(dx, dy) or 1.0
        offset_unit = None
        if a_id is not None and b_id is not None:
            offset_unit = self.canvas._bond_offset_unit_3d(a_id, b_id)
        if offset_unit is not None:
            nx, ny = offset_unit[0], offset_unit[1]
        else:
            nx = -dy / length
            ny = dx / length
        spacing = self.canvas.renderer.style.bond_spacing_px
        if count == 2:
            offsets = [-spacing / 2, spacing / 2]
        elif count == 3:
            offsets = [-spacing, 0.0, spacing]
        else:
            offsets = [0.0]

        t0, t1 = self.canvas._trim_line_for_labels(a_id, b_id, x1, y1, x2, y2)
        base_x1 = x1 + dx * t0
        base_y1 = y1 + dy * t0
        base_x2 = x1 + dx * t1
        base_y2 = y1 + dy * t1
        items = []
        for offset in offsets:
            ox = nx * offset
            oy = ny * offset
            line_item = NoSelectLineItem(base_x1 + ox, base_y1 + oy, base_x2 + ox, base_y2 + oy)
            line_item.setPen(self.canvas.renderer.bond_pen())
            items.append(line_item)
        return items

    def draw_wedge_bond(
        self,
        x1: float,
        y1: float,
        x2: float,
        y2: float,
        a_id: int | None = None,
        b_id: int | None = None,
    ):
        polygon = self._build_wedge_polygon(x1, y1, x2, y2, a_id, b_id)
        wedge_item = NoSelectPolygonItem(polygon)
        wedge_item.setPen(self.canvas.renderer.bond_pen())
        wedge_item.setBrush(QColor(self.canvas.renderer.style.bond_color))
        return [wedge_item]

    def draw_hash_bond(
        self,
        x1: float,
        y1: float,
        x2: float,
        y2: float,
        a_id: int | None = None,
        b_id: int | None = None,
    ):
        dx = x2 - x1
        dy = y2 - y1
        length = math.hypot(dx, dy) or 1.0
        count = max(3, int(length / self.canvas.renderer.style.hash_spacing_px))
        segments = self.hash_segments(x1, y1, x2, y2, count, a_id, b_id)
        items = []
        for seg in segments:
            line_item = NoSelectLineItem(*seg)
            line_item.setPen(self.canvas.renderer.bond_pen())
            items.append(line_item)
        return items

    def update_bond_geometry(self, bond_id: int) -> None:
        if not (0 <= bond_id < len(self.canvas.model.bonds)):
            return
        bond = self.canvas.model.bonds[bond_id]
        if bond is None:
            return
        items = self.canvas.bond_items.get(bond_id, [])
        if not items:
            return
        for item in items:
            self._reset_item_origin(item)
        a = self.canvas.model.atoms.get(bond.a)
        b = self.canvas.model.atoms.get(bond.b)
        if a is None or b is None:
            return
        if bond.style == "wedge":
            polygon = self.wedge_polygon(a.x, a.y, b.x, b.y, bond.a, bond.b)
            if isinstance(items[0], QGraphicsPolygonItem):
                items[0].setPolygon(polygon)
            return
        if bond.style == "hash":
            count = len(items)
            segments = self.hash_segments(a.x, a.y, b.x, b.y, count, bond.a, bond.b)
            for item, seg in zip(items, segments):
                if isinstance(item, QGraphicsLineItem):
                    item.setLine(*seg)
            return

        bold_style = bond.style in {"bold", "bold_in", "bold_out"}
        bold_outward = bond.style == "bold_out"
        if bold_style:
            if bond.order >= 2:
                ring_center = self.canvas._ring_center_for_bond(bond) if bond.order == 2 else None
                if bond.order == 2 and ring_center is not None and len(items) >= 2:
                    ring_center_3d = self.canvas._ring_center_3d_for_bond(bond)
                    outer_seg, inner_seg, (nx, ny) = self.ring_double_segments(
                        a, b, ring_center, bond.a, bond.b, center_3d=ring_center_3d
                    )
                    use_nx, use_ny = (nx, ny) if not bold_outward else (-nx, -ny)
                    outer_item = items[0]
                    if isinstance(outer_item, QGraphicsPolygonItem):
                        polygon = self.strip_polygon(
                            *outer_seg,
                            use_nx,
                            use_ny,
                            self.canvas.renderer.style.bond_line_width,
                            self.canvas.renderer.style.bold_bond_width * 1.5,
                        )
                        outer_item.setPolygon(polygon)
                    elif isinstance(outer_item, QGraphicsLineItem):
                        outer_item.setLine(*outer_seg)
                    inner_item = items[1]
                    if isinstance(inner_item, QGraphicsLineItem):
                        inner_item.setLine(*inner_seg)
                    return
                segments = self.parallel_bond_segments(
                    a.x, a.y, b.x, b.y, bond.order, bond.a, bond.b
                )
                if not segments:
                    return
                if isinstance(items[0], QGraphicsPolygonItem):
                    x1, y1, x2, y2 = segments[0]
                    nx, ny = self.canvas._line_normal(x1, y1, x2, y2, None)
                    if bold_outward:
                        nx, ny = -nx, -ny
                    polygon = self.strip_polygon(
                        x1,
                        y1,
                        x2,
                        y2,
                        nx,
                        ny,
                        self.canvas.renderer.style.bond_line_width,
                        self.canvas.renderer.style.bold_bond_width * 1.5,
                    )
                    items[0].setPolygon(polygon)
                elif isinstance(items[0], QGraphicsLineItem):
                    items[0].setLine(*segments[0])
                for item, seg in zip(items[1:], segments[1:]):
                    if isinstance(item, QGraphicsLineItem):
                        item.setLine(*seg)
                return
            bx1, by1 = a.x, a.y
            bx2, by2 = b.x, b.y
            ring_center = self.canvas._ring_center_for_bond(bond)
            scale = self._bold_out_scale(bold_outward, ring_center)
            bx1, by1, bx2, by2 = self._scale_segment(bx1, by1, bx2, by2, scale)
            pad = self.canvas.renderer.style.bond_length_px * 0.1
            bx1, by1, bx2, by2 = self._extend_segment(bx1, by1, bx2, by2, pad)
            dx = bx2 - bx1
            dy = by2 - by1
            bx1 = bx1 + dx * 0.025
            by1 = by1 + dy * 0.025
            bx2 = bx2 - dx * 0.025
            by2 = by2 - dy * 0.025
            nx, ny = self.canvas._line_normal(bx1, by1, bx2, by2, ring_center)
            if bold_outward:
                nx, ny = -nx, -ny
            if isinstance(items[0], QGraphicsPolygonItem):
                polygon = self.strip_polygon(
                    bx1,
                    by1,
                    bx2,
                    by2,
                    nx,
                    ny,
                    self.canvas.renderer.style.bond_line_width,
                    self.canvas.renderer.style.bold_bond_width * 1.5,
                )
                items[0].setPolygon(polygon)
            elif isinstance(items[0], QGraphicsLineItem):
                items[0].setLine(bx1, by1, bx2, by2)
            return

        if bond.order == 2:
            ring_center = self.canvas._ring_center_for_bond(bond)
            if ring_center is not None and len(items) >= 2:
                ring_center_3d = self.canvas._ring_center_3d_for_bond(bond)
                outer_seg, inner_seg, _ = self.ring_double_segments(
                    a, b, ring_center, bond.a, bond.b, center_3d=ring_center_3d
                )
                if isinstance(items[0], QGraphicsLineItem):
                    items[0].setLine(*outer_seg)
                if isinstance(items[1], QGraphicsLineItem):
                    items[1].setLine(*inner_seg)
                return
            segments = self.parallel_bond_segments(a.x, a.y, b.x, b.y, bond.order, bond.a, bond.b)
            for item, seg in zip(items, segments):
                if isinstance(item, QGraphicsLineItem):
                    item.setLine(*seg)
            return
        if bond.order >= 2:
            segments = self.parallel_bond_segments(a.x, a.y, b.x, b.y, bond.order, bond.a, bond.b)
            for item, seg in zip(items, segments):
                if isinstance(item, QGraphicsLineItem):
                    item.setLine(*seg)
            return

        t0, t1 = self.canvas._trim_line_for_labels(bond.a, bond.b, a.x, a.y, b.x, b.y)
        x1 = a.x + (b.x - a.x) * t0
        y1 = a.y + (b.y - a.y) * t0
        x2 = a.x + (b.x - a.x) * t1
        y2 = a.y + (b.y - a.y) * t1
        if isinstance(items[0], QGraphicsLineItem):
            items[0].setLine(x1, y1, x2, y2)

    def add_bond_graphics(self, bond_id: int) -> None:
        bond = self.canvas.model.bonds[bond_id]
        if bond is None:
            return
        a = self.canvas.model.atoms[bond.a]
        b = self.canvas.model.atoms[bond.b]
        items = []
        color = QColor(bond.color or self.canvas.renderer.style.bond_color)
        if bond.style == "wedge":
            items = self.draw_wedge_bond(a.x, a.y, b.x, b.y, bond.a, bond.b)
        elif bond.style == "hash":
            items = self.draw_hash_bond(a.x, a.y, b.x, b.y, bond.a, bond.b)
        elif bond.style in {"bold", "bold_in", "bold_out"}:
            bold_outward = bond.style == "bold_out"
            if bond.order >= 2:
                handled_outer = False
                if bond.order == 2:
                    ring_center = self.canvas._ring_center_for_bond(bond)
                    if ring_center is not None:
                        ring_center_3d = self.canvas._ring_center_3d_for_bond(bond)
                        outer_style = "bold_outward" if bold_outward else "bold_inward"
                        items = self.draw_ring_double_bond(
                            a,
                            b,
                            ring_center,
                            bond.a,
                            bond.b,
                            outer_style=outer_style,
                            center_3d=ring_center_3d,
                        )
                        handled_outer = True
                if not handled_outer:
                    items = self.draw_parallel_bonds(a.x, a.y, b.x, b.y, bond.order, bond.a, bond.b)
                    if items and isinstance(items[0], QGraphicsLineItem):
                        x1, y1, x2, y2 = (
                            items[0].line().x1(),
                            items[0].line().y1(),
                            items[0].line().x2(),
                            items[0].line().y2(),
                        )
                        nx, ny = self.canvas._line_normal(x1, y1, x2, y2, None)
                        if bold_outward:
                            nx, ny = -nx, -ny
                        items[0] = self.one_sided_bond_strip(
                            x1,
                            y1,
                            x2,
                            y2,
                            nx,
                            ny,
                            self.canvas.renderer.style.bond_line_width,
                            self.canvas.renderer.style.bold_bond_width * 1.5,
                        )
            else:
                bx1, by1 = a.x, a.y
                bx2, by2 = b.x, b.y
                ring_center = self.canvas._ring_center_for_bond(bond)
                scale = self._bold_out_scale(bold_outward, ring_center)
                bx1, by1, bx2, by2 = self._scale_segment(bx1, by1, bx2, by2, scale)
                pad = self.canvas.renderer.style.bond_length_px * 0.1
                bx1, by1, bx2, by2 = self._extend_segment(bx1, by1, bx2, by2, pad)
                dx = bx2 - bx1
                dy = by2 - by1
                bx1 = bx1 + dx * 0.025
                by1 = by1 + dy * 0.025
                bx2 = bx2 - dx * 0.025
                by2 = by2 - dy * 0.025
                nx, ny = self.canvas._line_normal(bx1, by1, bx2, by2, ring_center)
                if bold_outward:
                    nx, ny = -nx, -ny
                line_item = self.one_sided_bond_strip(
                    bx1,
                    by1,
                    bx2,
                    by2,
                    nx,
                    ny,
                    self.canvas.renderer.style.bond_line_width,
                    self.canvas.renderer.style.bold_bond_width * 1.5,
                )
                items = [line_item]
        elif bond.order == 2:
            ring_center = self.canvas._ring_center_for_bond(bond)
            if ring_center is not None:
                ring_center_3d = self.canvas._ring_center_3d_for_bond(bond)
                items = self.draw_ring_double_bond(
                    a,
                    b,
                    ring_center,
                    bond.a,
                    bond.b,
                    center_3d=ring_center_3d,
                )
            else:
                items = self.draw_parallel_bonds(a.x, a.y, b.x, b.y, bond.order, bond.a, bond.b)
        elif bond.order >= 2:
            items = self.draw_parallel_bonds(a.x, a.y, b.x, b.y, bond.order, bond.a, bond.b)
        else:
            t0, t1 = self.canvas._trim_line_for_labels(bond.a, bond.b, a.x, a.y, b.x, b.y)
            x1 = a.x + (b.x - a.x) * t0
            y1 = a.y + (b.y - a.y) * t0
            x2 = a.x + (b.x - a.x) * t1
            y2 = a.y + (b.y - a.y) * t1
            line_item = NoSelectLineItem(
                x1,
                y1,
                x2,
                y2,
            )
            line_item.setPen(self.canvas.renderer.bond_pen())
            items = [line_item]

        for item in items:
            item.setData(0, "bond")
            item.setData(1, bond_id)
            self.canvas._make_selectable(item)
            self.canvas._apply_color_to_bond_item(item, color)
            self.canvas.scene().addItem(item)
        self.canvas.bond_items[bond_id] = items
