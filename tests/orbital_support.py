from chemvas.domain.document import AnnotationCollection
from chemvas.ui.annotations.items import OrbitalItem


def make_orbital(
    canvas=None,
    *,
    center=(0.0, 0.0),
    kind="s",
    scale=1.0,
    rotation=0.0,
    base_handle_dist=24.0,
):
    document = (
        AnnotationCollection() if canvas is None else canvas.runtime_state.orbital_state
    )
    return OrbitalItem(
        {"center": center, "orbital_kind": kind, "scale": scale, "rotation": rotation},
        document,
        [],
        base_handle_dist,
    )
