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

Chemvas is an **open-source chemical drawing application** where chemists and automation scripts share the same editable canvas. Draw intuitively on the desktop canvas, automate edits or inspections through a dedicated CLI, and reopen the results anytime without losing editability.

## Features

- **Intuitive Canvas Drawing**: Sketch structures, insert SMILES, label reaction arrows, and align molecules with real-time feedback, autosave, and session recovery.
- **Headless Automation & CLI**: Inspect atom IDs, validate layouts, apply programmatic patches, and render publication figures without launching the GUI.
- **Publication-Ready Figure Export**: Export vector graphics (SVG, PDF) and raster images (PNG, TIFF) at exact publication column widths (e.g., 82 mm, 174 mm) while retaining full canvas editability.
- **Reliable Document Format**: Saved `.chemvas` documents remain fully editable JSON files (version 8, schema 1). See our [document compatibility policy](https://github.com/dhsohn/Chemvas/blob/main/docs/DOCUMENT_COMPATIBILITY.md).

## Install

Requires **Python 3.12+**.

To use chemical informatics features (SMILES insertion, molecular properties, 3D XYZ export, structure-based suggestions, and `pack-step`), install with the optional RDKit backend:

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

## Automation & CLI

Inspect, validate, and render documents directly from the command line:

```bash
chemvas inspect-document first-scheme.chemvas
chemvas check-layout first-scheme.chemvas
chemvas render-document first-scheme.chemvas --output first-scheme.pdf --width-mm 174
```

For more CLI workflows, see the [Agent CLI guide](https://github.com/dhsohn/Chemvas/blob/main/docs/AGENT_CLI.md), [Scheme Layout guide](https://github.com/dhsohn/Chemvas/blob/main/docs/SCHEME_LAYOUT.md), and [Publication Schemes guide](https://github.com/dhsohn/Chemvas/blob/main/docs/PUBLICATION_SCHEMES.md).

## Documentation

- [Drawing Tools & Shortcuts](https://github.com/dhsohn/Chemvas/blob/main/docs/REFERENCE.md) · [Chemistry I/O](https://github.com/dhsohn/Chemvas/blob/main/docs/REFERENCE.md#chemistry-io) · [Image Objects](https://github.com/dhsohn/Chemvas/blob/main/docs/IMAGE_OBJECTS.md)
- [Calculation Handoff (RDKit)](https://github.com/dhsohn/Chemvas/blob/main/docs/AGENT_CLI.md#calculation-states-and-elementary-steps): Export reaction steps with embedded components to `machine.json`.
- [Examples](https://github.com/dhsohn/Chemvas/tree/main/examples): Sample `.chemvas` documents (version 8, schema 1).
- [Architecture](https://github.com/dhsohn/Chemvas/blob/main/docs/ARCHITECTURE.md) · [Contributing](https://github.com/dhsohn/Chemvas/blob/main/CONTRIBUTING.md) · [Changelog](https://github.com/dhsohn/Chemvas/blob/main/CHANGELOG.md) · [Releasing](https://github.com/dhsohn/Chemvas/blob/main/RELEASING.md) · [License (MIT)](https://github.com/dhsohn/Chemvas/blob/main/LICENSE)

Feedback and bug reports: [GitHub Issues](https://github.com/dhsohn/Chemvas/issues).
