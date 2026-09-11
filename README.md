<p align="center">
  <img src="https://raw.githubusercontent.com/dhsohn/Chemvas/main/docs/images/banner.png" alt="Chemvas — Draw interactively. Automate safely. Export exactly." width="680">
</p>

<p align="center">
  <a href="https://github.com/dhsohn/Chemvas/actions/workflows/ci.yml"><img src="https://github.com/dhsohn/Chemvas/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
  <a href="https://pypi.org/project/chemvas/"><img src="https://img.shields.io/pypi/v/chemvas" alt="PyPI"></a>
  <a href="https://www.python.org/"><img src="https://img.shields.io/badge/python-3.12%2B-blue.svg" alt="Python 3.12+"></a>
  <a href="https://github.com/dhsohn/Chemvas/blob/main/LICENSE"><img src="https://img.shields.io/badge/License-MIT-blue.svg" alt="License: MIT"></a>
</p>

<p align="center"><b>English</b> · <a href="https://github.com/dhsohn/Chemvas/blob/main/README.ko.md">한국어</a></p>

Chemvas is an **open-source chemical drawing app where chemists and AI agents
work on the same editable canvas**. Start in the desktop app, let an agent
continue through a purpose-built CLI, then open the editable result right back
on the canvas.

## Draw it yourself. Hand it to AI. Keep editing.

- **Draw it yourself.** Sketch structures, insert SMILES, label reaction arrows,
  and align molecules on the desktop canvas, with autosave and crash recovery.
  SMILES insertion needs the optional RDKit backend.
- **Hand the same drawing to an AI agent.** The CLI can compose documents,
  inspect stable atom IDs, apply bounded graph patches, check layouts, and render
  figures without opening the desktop app. Graph Patch binds each proposal to the
  exact source hash and validates the complete result before writing a new file.
- **Keep editing the result.** Composed and patched drawings remain native,
  reopenable `.chemvas` documents. Export SVG, PDF, PNG, or TIFF at explicit
  physical sizes while keeping the editable drawing alongside the figure.

## Install

Requires **Python 3.12+**. Install the optional RDKit backend for SMILES insertion,
Molecule Info (formula and identifiers), 3D XYZ export, abbreviation MOL export,
**Suggest by structure**, and `generate-precomplex` / `select-precomplex` / `pack-step`:

```bash
pip install "chemvas[rdkit]"
chemvas
```

`pip install chemvas` skips RDKit. Drawing, `.chemvas` save/open, figure export
(SVG/PDF/PNG/TIFF, including editable SVG), and plain MOL import/export remain
available. Local Windows builds:
[packaging notes](https://github.com/dhsohn/Chemvas/blob/main/packaging/windows/README.md).

## Your first reaction scheme

![Chemvas walkthrough: insert structures, label an arrow, align the scheme, and export SVG](https://raw.githubusercontent.com/dhsohn/Chemvas/main/docs/images/demo.gif)

1. Choose **Ring**, type `OCc1ccccc1` in its SMILES field, click **Insert**, then
   click the canvas. Hover the oxygen, press **Enter**, label it `OH`.
2. Insert `O=Cc1ccccc1` to the right. Choose **Arrow**, drag between the two
   structures, then double-click the arrow to label it.
3. **Edit ▸ Select All**, then **Edit ▸ Align ▸ Middle**.
4. Save as `.chemvas`. **File ▸ Export Figure…** → **Plain SVG**,
   **Fit 2-column (174 mm)**.

The [step-by-step guide](https://github.com/dhsohn/Chemvas/blob/main/docs/FIRST_SCHEME.md)
has the label text and the downloadable files. The drawing is an exercise, not
an experimental result.

## Scripts

With the downloaded `first-scheme.chemvas`:

```bash
chemvas inspect-document first-scheme.chemvas
chemvas check-layout first-scheme.chemvas
chemvas render-document first-scheme.chemvas --output first-scheme.pdf --width-mm 174
```

Rendering writes a new file and never touches the source. Composition, Graph
Patch, scheme layout and their limits:
[document CLI guide](https://github.com/dhsohn/Chemvas/blob/main/docs/AGENT_CLI.md) ·
[scheme layout](https://github.com/dhsohn/Chemvas/blob/main/docs/SCHEME_LAYOUT.md) ·
[publication recipe](https://github.com/dhsohn/Chemvas/blob/main/docs/PUBLICATION_SCHEMES.md).

## Documentation

- [Drawing tools and shortcuts](https://github.com/dhsohn/Chemvas/blob/main/docs/REFERENCE.md) ·
  [Chemistry I/O](https://github.com/dhsohn/Chemvas/blob/main/docs/REFERENCE.md#chemistry-io) ·
  [Image objects](https://github.com/dhsohn/Chemvas/blob/main/docs/IMAGE_OBJECTS.md) ·
  [Limits and roadmap](https://github.com/dhsohn/Chemvas/blob/main/docs/REFERENCE.md#roadmap--not-yet-supported)
- [Calculation handoff (RDKit)](https://github.com/dhsohn/Chemvas/blob/main/docs/AGENT_CLI.md#calculation-states-and-elementary-steps): elementary steps and reviewed precomplexes, one `machine.json` per step.
- Documents are editable `.chemvas` JSON files (version 7).
  [More examples](https://github.com/dhsohn/Chemvas/tree/main/examples)
- [Contributing](https://github.com/dhsohn/Chemvas/blob/main/CONTRIBUTING.md) ·
  [Architecture](https://github.com/dhsohn/Chemvas/blob/main/docs/ARCHITECTURE.md) ·
  [Changelog](https://github.com/dhsohn/Chemvas/blob/main/CHANGELOG.md) ·
  [Releasing](https://github.com/dhsohn/Chemvas/blob/main/RELEASING.md) ·
  [MIT License](https://github.com/dhsohn/Chemvas/blob/main/LICENSE)

Something got in your way? [Open an issue](https://github.com/dhsohn/Chemvas/issues).
