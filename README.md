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

Chemvas is an **open-source chemical drawing application** designed for desktop drafting and publication-quality figure preparation. Draw structures and reaction schemes intuitively on the canvas, insert SMILES, align components, and export figures with exact journal dimensions.

## Features

- **Intuitive Canvas Drawing**: Sketch structures, insert SMILES, label reaction arrows, and align molecules with real-time feedback, autosave, and session recovery.
- **Publication-Ready Figure Export**: Export vector graphics (SVG, PDF) and raster images (PNG, TIFF) at exact publication column widths (e.g., 82 mm, 174 mm) while retaining full canvas editability.
- **Chemistry & 3D Preview**: Inspect molecular properties, view interactive 3D conformations, and export XYZ coordinates with optional RDKit integration.
- **Reliable Document Format**: Saved `.chemvas` documents remain fully editable JSON files (version 8, schema 1). See the [document compatibility policy](https://github.com/dhsohn/Chemvas/blob/main/docs/DOCUMENT_COMPATIBILITY.md).

## Install

Requires **Python 3.12+**.

To use chemical informatics features (SMILES insertion, molecular properties, 3D XYZ export, and structure suggestions), install with the optional RDKit backend:

```bash
pip install "chemvas[rdkit]"
chemvas
```

For basic drawing, document editing, and figure export without RDKit:

`pip install chemvas`

For local Windows packaging, see the [Windows packaging guide](https://github.com/dhsohn/Chemvas/blob/main/packaging/windows/README.md).

## Quickstart: Your First Reaction Scheme

![Chemvas walkthrough: insert structures, label an arrow, align the scheme, and export SVG](https://raw.githubusercontent.com/dhsohn/Chemvas/main/docs/images/demo.gif)

1. Type `OCc1ccccc1` in the SMILES field below the toolbar, click **Insert**, then click on the canvas. Hover over the oxygen atom, press **Enter**, and set the label to `OH`.
2. Insert `O=Cc1ccccc1` to the right. Select the **Arrow** tool, drag between the structures, and double-click the arrow to add condition labels.
3. Select both molecules (**Edit ▸ Select All**) and align them (**Edit ▸ Align ▸ Middle**).
4. Save the document (`.chemvas`). Export via **File ▸ Export Figure…** → **Plain SVG**, **Fit 2-column (174 mm)**.

For detailed instructions and example files, see the [step-by-step guide](https://github.com/dhsohn/Chemvas/blob/main/docs/FIRST_SCHEME.md).

## Documentation

- [Drawing Tools & Shortcuts](https://github.com/dhsohn/Chemvas/blob/main/docs/REFERENCE.md) · [Chemistry I/O](https://github.com/dhsohn/Chemvas/blob/main/docs/REFERENCE.md#chemistry-io) · [Image Objects](https://github.com/dhsohn/Chemvas/blob/main/docs/IMAGE_OBJECTS.md)
- [Calculation Handoff (RDKit)](https://github.com/dhsohn/Chemvas/blob/main/docs/AGENT_CLI.md#calculation-states-and-elementary-steps): Export reaction steps with embedded components to `machine.json`.
- [Headless & Agent CLI](https://github.com/dhsohn/Chemvas/blob/main/docs/AGENT_CLI.md) · [Scheme Layout](https://github.com/dhsohn/Chemvas/blob/main/docs/SCHEME_LAYOUT.md) · [Publication Schemes](https://github.com/dhsohn/Chemvas/blob/main/docs/PUBLICATION_SCHEMES.md)
- [Examples](https://github.com/dhsohn/Chemvas/tree/main/examples): Sample `.chemvas` documents (version 8, schema 1).
- [Architecture](https://github.com/dhsohn/Chemvas/blob/main/docs/ARCHITECTURE.md) · [Contributing](https://github.com/dhsohn/Chemvas/blob/main/CONTRIBUTING.md) · [Security](https://github.com/dhsohn/Chemvas/blob/main/SECURITY.md) · [Changelog](https://github.com/dhsohn/Chemvas/blob/main/CHANGELOG.md) · [Releasing](https://github.com/dhsohn/Chemvas/blob/main/RELEASING.md) · [License (MIT)](https://github.com/dhsohn/Chemvas/blob/main/LICENSE)

Feedback and bug reports: [GitHub Issues](https://github.com/dhsohn/Chemvas/issues).

## How this was built

I'm a chemist, not a programmer. AI coding agents write the code in this repository.
I decide what Chemvas should do, record structural decisions as
[architecture decision records](https://github.com/dhsohn/Chemvas/tree/main/docs/adr),
keep saved drawings under a written
[compatibility policy](https://github.com/dhsohn/Chemvas/blob/main/docs/DOCUMENT_COMPATIBILITY.md),
and set the checks a change must pass before it merges.

I don't review the code line by line, so a change is accepted on evidence, not on an
agent's report that it works:

- `make check` runs lint, formatting and type checks, then runs each test file in its
  own process so Qt state cannot leak from one file into the next. CI runs the same
  per-file suite.
- `machine.json` output is validated against the shared
  [machine-contracts](https://github.com/dhsohn/machine-contracts) validator. When the
  validator is missing, the check fails instead of passing silently.
- High-impact changes, such as the document format, undo and rollback, and figure
  export, get an independent adversarial review from a separate agent.
