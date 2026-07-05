from __future__ import annotations

from collections.abc import Callable
from typing import Any

from ui.structure_fragment_build_service import FRAGMENT_BUILD_FAILED

REGULAR_RING_TEMPLATES = {
    "cyclopropane": 3,
    "cyclobutane": 4,
    "cyclopentane": 5,
}

HETERO_RING_TEMPLATES = {
    "pyridine": (6, ["C", "C", "C", "C", "C", "N"]),
    "pyrimidine": (6, ["N", "C", "N", "C", "C", "C"]),
    "imidazole": (5, ["C", "N", "C", "N", "C"]),
    "pyrrole": (5, ["N", "C", "C", "C", "C"]),
    "furan": (5, ["O", "C", "C", "C", "C"]),
    "thiophene": (5, ["S", "C", "C", "C", "C"]),
    "pyranose": (6, ["O", "C", "C", "C", "C", "C"]),
    "furanose": (5, ["O", "C", "C", "C", "C"]),
}

FUSED_BENZENE_TEMPLATES = {
    "naphthalene": (2, "linear"),
    "anthracene": (3, "linear"),
    "phenanthrene": (3, "angled"),
}

CROWN_ETHER_TEMPLATES = {
    "crown_12_4": (12, 4),
    "crown_15_5": (15, 5),
    "crown_18_6": (18, 6),
}

HETERO_RING_BOND_ORDERS = {
    "pyridine": [2, 1, 2, 1, 2, 1],
    "pyrimidine": [2, 1, 2, 1, 2, 1],
    "imidazole": [1, 2, 1, 1, 2],
    "pyrrole": [1, 2, 1, 2, 1],
    "furan": [1, 2, 1, 2, 1],
    "thiophene": [1, 2, 1, 2, 1],
}

SERVICE_TEMPLATE_METHODS = {
    "cyclohexane_chair": "add_cyclohexane_chair",
    "cyclohexane_boat": "add_cyclohexane_boat",
    "indole": "add_indole",
    "quinoline": "add_quinoline",
    "isoquinoline": "add_isoquinoline",
    "benzimidazole": "add_benzimidazole",
    "phenyl": "add_phenyl",
    "benzyl": "add_benzyl",
    "vinyl": "add_vinyl",
    "allyl": "add_allyl",
    "carboxyl": "add_carboxyl",
    "nitro": "add_nitro",
    "sulfonyl": "add_sulfonyl",
    "carbonyl": "add_carbonyl",
    "tbu": "add_tbu",
    "ipr": "add_ipr",
    "me": "add_me",
    "et": "add_et",
    "peptide_2": "add_peptide_2",
}


def apply_structure_template_command(service, key: str) -> None:
    template_builder = service.template_builder
    if key in REGULAR_RING_TEMPLATES:
        n = REGULAR_RING_TEMPLATES[key]
        service.run_recorded_build(_successful_template_action(lambda: template_builder.add_regular_ring_template(n)))
        return
    if key in HETERO_RING_TEMPLATES:
        n, elements = HETERO_RING_TEMPLATES[key]
        bond_orders = HETERO_RING_BOND_ORDERS.get(key)
        service.run_recorded_build(
            _successful_template_action(lambda: template_builder.add_hetero_ring_template(n, elements, bond_orders))
        )
        return
    if key in FUSED_BENZENE_TEMPLATES:
        count, mode = FUSED_BENZENE_TEMPLATES[key]
        service.run_recorded_build(_successful_template_action(lambda: template_builder.add_fused_benzenes(count, mode=mode)))
        return
    if key in CROWN_ETHER_TEMPLATES:
        atoms, oxygens = CROWN_ETHER_TEMPLATES[key]
        service.run_recorded_build(_successful_template_action(lambda: template_builder.add_crown_ether(atoms, oxygens)))
        return
    method_name = SERVICE_TEMPLATE_METHODS.get(key)
    if method_name is not None:
        getattr(template_builder, method_name)()
        return
    raise ValueError(f"Unknown structure template: {key}")


def _successful_template_action(action: Callable[[], Any]) -> Callable[[], list | None]:
    def _action() -> list | None:
        result = action()
        if result is FRAGMENT_BUILD_FAILED:
            return None
        if isinstance(result, list):
            return result
        return []

    return _action


def known_structure_template_keys() -> tuple[str, ...]:
    return tuple(
        (
            *REGULAR_RING_TEMPLATES,
            *HETERO_RING_TEMPLATES,
            *FUSED_BENZENE_TEMPLATES,
            *CROWN_ETHER_TEMPLATES,
            *SERVICE_TEMPLATE_METHODS,
        )
    )


__all__ = [
    "CROWN_ETHER_TEMPLATES",
    "FUSED_BENZENE_TEMPLATES",
    "HETERO_RING_BOND_ORDERS",
    "HETERO_RING_TEMPLATES",
    "REGULAR_RING_TEMPLATES",
    "SERVICE_TEMPLATE_METHODS",
    "apply_structure_template_command",
    "known_structure_template_keys",
]
