"""Structured export failures shared by desktop and command-line callers."""

from __future__ import annotations


class MinimumFontSizeError(ValueError):
    """Keep CLI diagnostics while exposing measured values to the desktop."""

    def __init__(
        self,
        minimum_pt: float,
        required_pt: float,
        witness: dict[str, object] | None,
    ) -> None:
        self.minimum_pt = minimum_pt
        self.required_pt = required_pt
        self.witness = witness
        super().__init__(
            f"minimum visible font is {minimum_pt:.6f} pt at {witness}; "
            f"below --min-font-pt {required_pt:g}; output was not resized"
        )


class MaximumHeightError(ValueError):
    """Expose final output height without changing the CLI failure message."""

    def __init__(self, height_mm: float, maximum_mm: float) -> None:
        self.height_mm = height_mm
        self.maximum_mm = maximum_mm
        super().__init__(
            f"rendered height exceeds --max-height-mm {maximum_mm:g}; "
            "output was not resized"
        )
