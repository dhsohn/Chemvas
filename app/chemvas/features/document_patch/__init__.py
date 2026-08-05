"""Strict, provider-neutral graph inspection and patch contracts."""

from .service import (
    DOCUMENT_PATCH_FORMAT,
    DOCUMENT_PATCH_VERSION,
    MAX_PATCH_OPERATIONS,
    DocumentPatchResult,
    apply_document_patch,
    inspect_document_graph,
)

__all__ = [
    "DOCUMENT_PATCH_FORMAT",
    "DOCUMENT_PATCH_VERSION",
    "MAX_PATCH_OPERATIONS",
    "DocumentPatchResult",
    "apply_document_patch",
    "inspect_document_graph",
]
