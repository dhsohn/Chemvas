<p align="center">
  <img src="https://raw.githubusercontent.com/dhsohn/Chemvas/main/docs/images/banner.png" alt="Chemvas — 2D chemical structure drawing canvas" width="680">
</p>

<p align="center">
  <a href="https://github.com/dhsohn/Chemvas/actions/workflows/ci.yml"><img src="https://github.com/dhsohn/Chemvas/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
  <a href="https://pypi.org/project/chemvas/"><img src="https://img.shields.io/pypi/v/chemvas" alt="PyPI"></a>
  <a href="https://www.python.org/"><img src="https://img.shields.io/badge/python-3.12%2B-blue.svg" alt="Python 3.12+"></a>
  <a href="https://github.com/dhsohn/Chemvas/blob/main/LICENSE"><img src="https://img.shields.io/badge/License-MIT-blue.svg" alt="License: MIT"></a>
</p>

<p align="center"><b>English</b> · <a href="https://github.com/dhsohn/Chemvas/blob/main/README.ko.md">한국어</a></p>

Chemvas is a lightweight PyQt6 app for **drawing 2D chemical structures and
reaction schemes** — ACS 1996 defaults, ChemDraw-compatible shortcuts, and
publication-ready figure export. Draw fast, export exactly.

![Chemvas — a C–P bond cleavage reaction scheme (KOtBu / THF) drawn on the canvas](https://raw.githubusercontent.com/dhsohn/Chemvas/main/docs/images/demo.png)

## Statement of need

Sketching a scheme for a lab notebook or paper should not require a commercial
suite — and automating edits should not mean trusting an LLM with your drawing.
Chemvas keeps the interactive canvas small and fast, and exposes headless
CLI contracts for rendering, inspection, editing, and calculation handoff:
document edits bind to the exact source hash and unsupported input fails
closed. Agents propose, validation decides.

## Quickstart

```bash
pip install chemvas              # core (PyQt6 included)
pip install "chemvas[rdkit]"     # + SMILES import, formula/weight, calculation handoff, 3D
chemvas
```

Pick a tool from the toolbar and click/drag on the canvas. Type a SMILES string
and press **Insert** to preview and place it *(RDKit)*. Open
[examples/template2.chemvas](https://github.com/dhsohn/Chemvas/blob/main/examples/template2.chemvas) via **File ▸ Open** to
explore the document shown above.

## What it does

| Capability | Use it for | Details |
|---|---|---|
| **Drawing** | bonds, rings, arrows, brackets, atom labels — with ChemDraw-compatible shortcuts | [REFERENCE](https://github.com/dhsohn/Chemvas/blob/main/docs/REFERENCE.md) |
| **Figure export** | plain SVG / PDF / PNG / TIFF, outlined glyphs, deterministic physical sizing | [REFERENCE](https://github.com/dhsohn/Chemvas/blob/main/docs/REFERENCE.md#figure-export) |
| **Chemistry I/O** | SMILES import, `.mol` interchange, 2D→3D `.xyz`, Molecule Info *(RDKit)* | [REFERENCE](https://github.com/dhsohn/Chemvas/blob/main/docs/REFERENCE.md#chemistry-io) |
| **Agent CLI** | headless compose / layout-check / render / inspect / hash-gated Graph Patch, no Qt window | [AGENT_CLI](https://github.com/dhsohn/Chemvas/blob/main/docs/AGENT_CLI.md) |
| **Calculation handoff** | elementary steps, reviewed precomplexes, one `machine.json` per step *(RDKit)* | [AGENT_CLI](https://github.com/dhsohn/Chemvas/blob/main/docs/AGENT_CLI.md#calculation-states-and-elementary-steps) |

Documents are `.chemvas` files (JSON, version 7 contract) with autosave and
crash recovery; everything except the marked *(RDKit)* features runs without
RDKit.

## Development, testing, and full docs

- `make check` runs the whole local gate — lint, formatting, mypy, the
  file-isolated headless test suite, and the `machine.json` conformance check.
  Read [CONTRIBUTING.md](https://github.com/dhsohn/Chemvas/blob/main/CONTRIBUTING.md) before moving code: the architecture
  boundaries are enforced by tests.
- Docs index: [REFERENCE](https://github.com/dhsohn/Chemvas/blob/main/docs/REFERENCE.md) · [AGENT_CLI](https://github.com/dhsohn/Chemvas/blob/main/docs/AGENT_CLI.md) ·
  [ARCHITECTURE](https://github.com/dhsohn/Chemvas/blob/main/docs/ARCHITECTURE.md) · [CHANGELOG](https://github.com/dhsohn/Chemvas/blob/main/CHANGELOG.md) ·
  [RELEASING](https://github.com/dhsohn/Chemvas/blob/main/RELEASING.md)
- Known gaps (SDF interchange, one-file binaries, multi-molecule 3D export) →
  [roadmap](https://github.com/dhsohn/Chemvas/blob/main/docs/REFERENCE.md#roadmap--not-yet-supported)

## License

[MIT License](https://github.com/dhsohn/Chemvas/blob/main/LICENSE)
