from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from types import MappingProxyType
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Mapping

CURRENT_PROFILE_ID = "chemvas-rigid-precomplex-placement/2"


@dataclass(frozen=True)
class PrecomplexPlacementProfile:
    id: str
    approach_sample_count: int
    rotation_sample_count: int
    max_candidates: int
    radii: Mapping[str, tuple[float, float]]
    radius_table_sha256: str
    provenance_status: str


def _profile(
    profile_id: str,
    radii: dict[str, tuple[float, float]],
    *,
    provenance_status: str,
) -> PrecomplexPlacementProfile:
    canonical = json.dumps(
        {
            symbol: {
                "covalent_angstrom": covalent,
                "van_der_waals_angstrom": van_der_waals,
            }
            for symbol, (covalent, van_der_waals) in sorted(radii.items())
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return PrecomplexPlacementProfile(
        id=profile_id,
        approach_sample_count=12,
        rotation_sample_count=6,
        max_candidates=16,
        radii=MappingProxyType(radii),
        radius_table_sha256=hashlib.sha256(canonical.encode("ascii")).hexdigest(),
        provenance_status=provenance_status,
    )


# Profile 2 uses one cited definition for every supported element. Covalent
# radii are from Cordero et al., Dalton Trans. (2008), Table 2; carbon uses the
# sp3 entry and Fe/Co use the low-spin entries because the document model does
# not encode the coordination/spin information needed to choose another row.
# Van der Waals radii are from Alvarez, Dalton Trans. (2013), Table 1.
_CURRENT_PROFILE = _profile(
    CURRENT_PROFILE_ID,
    {
        "H": (0.31, 1.20),
        "Li": (1.28, 2.12),
        "B": (0.84, 1.91),
        "C": (0.76, 1.77),
        "N": (0.71, 1.66),
        "O": (0.66, 1.50),
        "F": (0.57, 1.46),
        "Na": (1.66, 2.50),
        "Mg": (1.41, 2.51),
        "Al": (1.21, 2.25),
        "Si": (1.11, 2.19),
        "P": (1.07, 1.90),
        "S": (1.05, 1.89),
        "Cl": (1.02, 1.82),
        "K": (2.03, 2.73),
        "Ca": (1.76, 2.62),
        "Fe": (1.32, 2.44),
        "Co": (1.26, 2.40),
        "Ni": (1.24, 2.40),
        "Cu": (1.32, 2.38),
        "Zn": (1.22, 2.39),
        "Br": (1.20, 1.86),
        "Ru": (1.46, 2.46),
        "Rh": (1.42, 2.44),
        "Pd": (1.39, 2.15),
        "Ag": (1.45, 2.53),
        "Sn": (1.39, 2.42),
        "I": (1.39, 2.04),
        "Ir": (1.41, 2.41),
        "Pt": (1.36, 2.29),
        "Au": (1.36, 2.32),
    },
    provenance_status="cited",
)

_PROFILES = MappingProxyType({_CURRENT_PROFILE.id: _CURRENT_PROFILE})


def precomplex_placement_profile(profile_id: object) -> PrecomplexPlacementProfile:
    if not isinstance(profile_id, str):
        raise ValueError("Precomplex placement profile id must be a string.")
    try:
        return _PROFILES[profile_id]
    except KeyError as exc:
        raise ValueError(
            f"Unsupported precomplex placement profile: {profile_id}"
        ) from exc


def radius_provenance_for(profile_id: str) -> dict[str, object]:
    profile = precomplex_placement_profile(profile_id)
    return {
        "status": profile.provenance_status,
        "units": "angstrom",
        "radius_table_sha256": profile.radius_table_sha256,
        "covalent": {
            "dataset_id": "cordero-2008-table-2",
            "doi": "10.1039/B801115J",
            "selectors": {"C": "sp3", "Fe": "low_spin", "Co": "low_spin"},
        },
        "van_der_waals": {
            "dataset_id": "alvarez-2013-table-1",
            "doi": "10.1039/C3DT50599E",
        },
    }


__all__ = [
    "CURRENT_PROFILE_ID",
    "PrecomplexPlacementProfile",
    "precomplex_placement_profile",
    "radius_provenance_for",
]
