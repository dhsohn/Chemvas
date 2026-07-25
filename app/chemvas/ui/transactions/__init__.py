"""Qt-aware transaction savepoints shared by legacy UI workflows."""

from __future__ import annotations

from .document import DocumentSavepoint, document_transaction

__all__ = ["DocumentSavepoint", "document_transaction"]
