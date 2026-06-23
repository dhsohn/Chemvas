# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

<!--
On the first tagged release, rename the "Unreleased" section below to
"## [0.1.0] - YYYY-MM-DD" and start a fresh empty "Unreleased" section above it.
-->

## [Unreleased]

### Added
- 2D drawing canvas: bonds (single/double/triple, bold, wedge, hash) with 30° angle
  snapping and a consistent default bond length.
- Ring and conformer templates (benzene, cycloalkanes, chair/boat) with live
  preview and click-to-insert.
- Arrows: reaction, equilibrium, resonance, curved, and dashed, with adjustable
  width and head scale.
- Bracket annotations (square/round/curly) plus dagger (`†`) and double dagger (`‡`)
  objects.
- Atom labels with charges, radicals, and common alias labels
  (`Me`, `Et`, `OH`, `Ph`, `OMe`, `Boc`, `CO2Me`, `t-Bu`, `i-Pr`).
- SMILES import with cursor preview and click-to-place (requires RDKit).
- Molecule Info window with interactive 3D preview and molecular formula/weight
  (requires RDKit).
- Canonical SMILES, InChI, and InChIKey computation for the current structure;
  the Molecule Info window gained **Copy SMILES** / **Copy InChIKey** buttons that
  place the value on the clipboard (requires RDKit).
- **Export MOL** (File menu): write the current structure to an MDL Molfile (`.mol`,
  V2000), preserving 2D coordinates, bond orders, and wedge/hash stereo. Works
  without RDKit.
- Figure export to SVG / PDF / PNG / TIFF with outlined glyphs and deterministic
  physical sizing (bond-length or 84/174 mm column fit).
- 2D→3D `.xyz` export of the current molecule or atom/bond selection, carrying
  charges/radicals and wedge/hash stereo (requires RDKit).
- Editing: select/move, horizontal & vertical flip, perspective rotation, and
  delta-based undo/redo.
- ChemDraw-compatible keyboard shortcut subset.
- `.chemvas` JSON document save/load (`{"type":"chemvas","version":1,...}`).
- ACS 1996 default style and color palette.

[Unreleased]: https://github.com/dhsohn/Chemvas/commits/main
