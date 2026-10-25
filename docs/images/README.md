# Demo and Branding Media

[한국어](README.ko.md)

Media assets used across README, documentation, and social previews.

The six GIFs and `demo.png` were recaptured on 2026-10-25 with Chemvas 0.27.1,
PyQt/Qt 6.11.0 and macOS arm64, using Qt's offscreen backend. They show the real
current widgets with scripted input and synthetic drawings. Captions are added
above the captured window. The capture profile isolates recent files and recovery
data on every OS; these recordings are documentation, not native installer tests.

| Asset | Source and purpose |
| --- | --- |
| `examples/first-scheme.png` | 300 DPI, 174 mm PNG export; completed result shown in README. |
| `examples/first-scheme.svg` | Plain SVG with 174 mm preset and outlined labels. |
| `demo.gif` | Qt UI walkthrough with section captions. |
| `demo.png` | Still frame of the completed application workspace. |
| `walkthrough-drawing.gif` | Reference guide: drawing bonds, keyboard shortcuts, charges, and fused rings. |
| `walkthrough-arrows.gif` | Reference guide: reaction arrows, equilibrium arrows, curved arrows, and profile connectors. |
| `walkthrough-editing.gif` | Reference guide: move, rotate, flip, align, and distribute actions. |
| `walkthrough-chemistry.gif` | Current MOL import and V2000 export of selected explicit atoms. |
| `walkthrough-images.gif` | Image objects: PNG insertion, resizing, and property adjustment. |
| `cli-*.png` | Visual figures for CLI commands and automated layout steps. |
| `examples/publication-*.png` | High-resolution publication figures shown in the example gallery. |
| `banner.png` | Chemvas banner rendered at 1360×270. |
| `social-preview.png` | 1280×640 social preview card for repository sharing. |

## Regenerating Walkthrough Animations

Capture the main demo workflow:

```bash
python -m pip install -e ".[dev]"
QT_QPA_PLATFORM=offscreen PYTHONPATH=app python scripts/capture_first_scheme.py --output-dir /tmp/chemvas-demo-capture
```

Use a new, empty output directory for each capture. Review the arrow-label
formatting, complete bond strokes and export-preview frames before replacing assets.
The demo uses Ring and Bond tools, selects the `2` in `MnO2`, applies **Subscript x₂**,
and saves the editable CDXML before exporting the figure.
Both benzene rings remain upright; the side chains use matching 30° zigzags
and the hydroxyl label reads horizontally.

Copy the generated assets:

```bash
cp /tmp/chemvas-demo-capture/first-scheme.cdxml examples/first-scheme.cdxml
cp /tmp/chemvas-demo-capture/first-scheme.svg examples/first-scheme.svg
cp /tmp/chemvas-demo-capture/first-scheme.png examples/first-scheme.png
cp /tmp/chemvas-demo-capture/demo.gif docs/images/demo.gif
cp /tmp/chemvas-demo-capture/demo.png docs/images/demo.png
```

Verify document inspection and headless rendering:

```bash
chemvas inspect-document examples/first-scheme.cdxml
chemvas check-layout examples/first-scheme.cdxml
chemvas render-document examples/first-scheme.cdxml --output /tmp/first-scheme-check.svg
```

## Regenerating Topic Walkthroughs

Generate individual topic GIFs (`--topic drawing|arrows|editing|chemistry|images`):

```bash
QT_QPA_PLATFORM=offscreen PYTHONPATH=app python scripts/capture_walkthroughs.py --output-dir /tmp/chemvas-walkthroughs
cp /tmp/chemvas-walkthroughs/walkthrough-*.gif docs/images/
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
