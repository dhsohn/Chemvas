"""Shared diagnostics for the optional chemistry backend."""

RDKIT_INSTALL_COMMAND = 'pip install "chemvas[rdkit]"'

RDKIT_UNAVAILABLE_MESSAGE = (
    "RDKit is not available in this environment. "
    f"Install it with: {RDKIT_INSTALL_COMMAND}."
)
