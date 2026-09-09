"""Explicit scheme layout and scoped presentation request contracts."""

from .service import (
    MAX_LAYOUT_BLOCKS,
    MAX_LAYOUT_REFERENCES,
    MAX_LAYOUT_ROWS,
    LayoutBlock,
    LayoutRequest,
    LayoutRow,
    merged_layout_groups,
    validate_layout_request,
    wrap_layout_row,
)

__all__ = [
    "MAX_LAYOUT_BLOCKS",
    "MAX_LAYOUT_REFERENCES",
    "MAX_LAYOUT_ROWS",
    "LayoutBlock",
    "LayoutRequest",
    "LayoutRow",
    "merged_layout_groups",
    "validate_layout_request",
    "wrap_layout_row",
]
