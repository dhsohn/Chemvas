"""Preserve document opacity separately from Qt's quantized paint channel."""

from PyQt6.QtCore import Qt

# Role 6 is already included by the canonical exact scene savepoint. Ring
# items do not otherwise use it, and this paint witness is not document data.
RING_FILL_ALPHA_ROLE = 6


def set_ring_fill_brush(item, brush, *, source_alpha: float | None = None) -> None:
    item.setBrush(brush)
    item.setData(
        RING_FILL_ALPHA_ROLE,
        None
        if source_alpha is None
        else {
            "alpha": source_alpha,
            "painted_alpha": item.brush().color().alphaF(),
        },
    )


def ring_fill_alpha(item) -> float:
    brush = item.brush()
    if brush.style() == Qt.BrushStyle.NoBrush:
        return 0.0
    painted_alpha = brush.color().alphaF()
    source = item.data(RING_FILL_ALPHA_ROLE)
    if isinstance(source, dict) and source.get("painted_alpha") == painted_alpha:
        alpha = source.get("alpha")
        if isinstance(alpha, (int, float)):
            return float(alpha)
    # Direct paint changes without a document alpha remain authoritative.
    return painted_alpha
