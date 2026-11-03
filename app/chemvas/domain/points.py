"""The point shape shared by Qt and Qt-free geometry callers.

Services that only read coordinates accept any object with ``x()``/``y()``
accessors, so the desktop passes ``QPointF`` and the browser editor passes its
own point type through the same typed signatures.
"""

from __future__ import annotations

from typing import Protocol


class PointLike(Protocol):
    """Any point read through ``x()``/``y()`` accessors (e.g. ``QPointF``)."""

    def x(self) -> float: ...

    def y(self) -> float: ...


__all__ = ["PointLike"]
