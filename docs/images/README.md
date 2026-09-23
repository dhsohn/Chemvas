# Demo and Branding Media

[한국어](README.ko.md)

Media assets used across README, documentation, and social previews.

| Asset | Source and purpose |
| --- | --- |
| `examples/first-scheme.png` | 300 DPI, 174 mm PNG export; completed result shown in README. |
| `examples/first-scheme.svg` | Plain SVG with 174 mm preset and outlined labels. |
| `demo.gif` | Qt UI walkthrough with section captions. |
| `demo.png` | Still frame of the completed application workspace. |
| `walkthrough-drawing.gif` | Reference guide: drawing bonds, keyboard shortcuts, charges, and fused rings. |
| `walkthrough-arrows.gif` | Reference guide: reaction arrows, equilibrium arrows, curved arrows, and profile connectors. |
| `walkthrough-editing.gif` | Reference guide: move, rotate, flip, align, and distribute actions. |
| `walkthrough-chemistry.gif` | Reference guide: molfile import, Molecule Info dock, and 3D XYZ export. |
| `walkthrough-images.gif` | Image objects: PNG insertion, resizing, and property adjustment. |
| `walkthrough-arrange.gif` | Scheme layout: grouping structures with captions and running Arrange Scheme. |
| `cli-*.png` | Visual figures for CLI commands and automated layout steps. |
| `examples/publication-*.png` | High-resolution publication figures shown in the example gallery. |
| `banner.png` | Chemvas banner rendered at 1360×270. |
| `social-preview.png` | 1280×640 social preview card for repository sharing. |

## Regenerating Walkthrough Animations

Capture the main demo workflow:

```bash
python -m pip install -e ".[dev,rdkit]"
QT_QPA_PLATFORM=offscreen python scripts/capture_first_scheme.py --output-dir /tmp/chemvas-demo-capture
```

Copy the generated assets:

```bash
cp /tmp/chemvas-demo-capture/first-scheme.chemvas examples/first-scheme.chemvas
cp /tmp/chemvas-demo-capture/first-scheme.svg examples/first-scheme.svg
cp /tmp/chemvas-demo-capture/first-scheme.png examples/first-scheme.png
cp /tmp/chemvas-demo-capture/demo.gif docs/images/demo.gif
cp /tmp/chemvas-demo-capture/demo.png docs/images/demo.png
```

Verify document inspection and headless rendering:

```bash
chemvas inspect-document examples/first-scheme.chemvas
chemvas check-layout examples/first-scheme.chemvas
chemvas render-document examples/first-scheme.chemvas --output /tmp/first-scheme-check.svg
```

## Regenerating Topic Walkthroughs

Generate individual topic GIFs (`--topic drawing|arrows|editing|chemistry|images|arrange`):

```bash
QT_QPA_PLATFORM=offscreen python scripts/capture_walkthroughs.py --output-dir /tmp/chemvas-walkthroughs
```

## Regenerating CLI and Publication Figures

Generate CLI diagram screenshots and publication scheme figures:

```bash
QT_QPA_PLATFORM=offscreen python scripts/render_doc_figures.py --output-dir /tmp/chemvas-doc-figures
```

Deploy the generated images:

```bash
cp /tmp/chemvas-doc-figures/figures/cli-*.png docs/images/
cp /tmp/chemvas-doc-figures/figures/publication-*.png examples/
```

## Regenerating Branding Assets

Rebuild the banner and social preview cards from the master assets:

```bash
QT_QPA_PLATFORM=offscreen python scripts/generate_branding_images.py
```
