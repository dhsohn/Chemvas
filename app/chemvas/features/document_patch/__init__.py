"""Strict, provider-neutral graph inspection and patch contracts."""

from .service import (
    MAX_PATCH_OPERATIONS,
    DocumentPatchResult,
    apply_document_patch,
    inspect_document_graph,
)

__all__ = [
    "MAX_PATCH_OPERATIONS",
    "DocumentPatchResult",
    "apply_document_patch",
    "inspect_document_graph",
]
