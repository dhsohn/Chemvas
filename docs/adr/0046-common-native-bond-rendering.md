# ADR 0046: One native bond convention for existing and new drawings

- Status: Proposed implementation; rendering policy approved by the user
- Date: 2026-10-11
- Supersedes: ADR 0017's non-double Bold inward/outward toggle

The user explicitly chose the same ChemDraw-style bond convention for existing
and new documents, without a legacy renderer, per-version switch or separate
export mode. Opening does not rewrite source bytes. Atom coordinates, bond ends,
orders, labels, charges and fragment attachments remain document data; rendering
does not migrate or repair them. The supported v7/v8/v9 reader and v9 writer are
unchanged. An old file deliberately gains the new appearance when rendered.

Single bold_in and bold_out are centered strokes of the same effective width.
Their persisted tokens remain readable. Applying Bold to an already-bold single
is a no-op rather than an invisible toggle. Click and drag retain one common
edit policy and preserve order and double alignment.

For plain doubles, double (including order-2 single tokens) keeps a full primary
axis and the secondary stroke toward the ring center/substituent side;
double_outer keeps that axis and places the secondary stroke on the opposite
side. double_center places its strokes on opposite sides of the axis. The
secondary end inset follows adjacent-bond angular bisectors, not a fixed 12%
shortening. Endpoint label clearance remains owned by scene geometry. Acute
insets and miters are bounded. Projected rings retain their projected geometry
with these same position meanings; perspective CDXML remains refused.

BondGeometryPlanService owns the primitives for build and in-place updates.
Single/Bold/double previews use that planner too. BondLineGeometryService computes
Qt-free stroke corners. BondStrokeItem retains the chemical centerline while
painting that outline, with matching bounds/shape and selection geometry. The
headless browser adapter serializes the same primitive outline. Ordinary single
strokes also use the shared end joins so adjacent round caps do not invalidate
the measured double-bond junction. Stereo/hash, dotted and triple families retain
their separate established primitive paths; bold/dotted double positions follow
the common segment placement, but unsupported native encodings remain refused.

CDXML retains real chemical bonds. Both single Bold tokens emit Display=Bold;
double_outer now has a native side placement. Existing native SVG controls show
positive page-normal displacement corresponds to CDXML Left, so the previous
side inversion is corrected. Per-bond BondSpacing is derived from the two drawn
centerlines and actual B-E distance, including the 1.1 spacing factor. Native
save/reopen controls at lengths 20, 40 and 80 showed that using inherited
BondLength instead would incorrectly multiply spacing by 1, 2 and 4.
The consumer truncates this percentage to tenths on save: a length-80 control
reopens at 4.80 pt instead of the 4.84 pt target. This consumer quantization is
recorded rather than hidden by moving atoms or changing the screen geometry.
No decorative graphics or hidden atom movement replace a chemical bond.

## Dependency and failure recovery correction

Moving A in an unlabeled A-B-C chain changes BC's end join and double-bond inset,
even while B and C stay fixed. CanvasMoveController therefore refreshes edges at
both ends of every movement-boundary edge, including selected internal edges
whose outside angle changes. Whole-component translation retains its existing
item-translation path. Absolute position application, 2D/3D rotation and history
replay use the same dependency-aware refresh.

The transaction savepoint also captures BondStrokeItem's stored paint polygon as
raw graphics state. If both a commit and the redraw callback fail, restoring the
centerline alone is insufficient. The raw snapshot restores the outline without
depending on that failing callback. Pointer-frame, release, reopen/export,
Undo/Redo and failed-commit regressions protect these existing workflows.

The initial product witness covers four planar unlabeled six-membered-ring side
and endpoint-direction cases, two isolated Bold cases, and all thirty painted
strokes including adjacent single joins. It compares calculated geometry against
previously saved native SVG, not copied measurement arrays. General ChemDraw
appearance and all native editing workflows require broader verification.

## Adapter and insertion integration corrections

The browser's deferred renderer implements the geometry-update callback used by
the shared move controller. It does not create intermediate graphics; the public
edit path materializes the accepted document once. A Qt-free public atom-move
regression protects that boundary. Browser atom placement uses the same measured
em/descent baseline rule as the desktop; free marks retain their separate
document-centered placement.

A browser line primitive retains both its chemical centerline and, when present,
its explicit paint polygon. SVG paint and scene bounds use the polygon. Selection
and editing retain the centerline and the existing selection-width policy, as the
desktop does. Tests compare both pieces with real native items and check that the
SVG consumer does not paint a duplicate centerline.

Whole-model drawing rebuilds the owned graph indexes before rendering. A completed
ring insertion refreshes pre-existing joins after all new edges and its ring fill
exist. Topology mutation and movement share the same graph dependency calculation,
including edges at both ends of a changed boundary. Live/fresh-scene comparisons
cover two sequential insertions, Undo and Redo without moving document atoms.
Rollback expectations remain exact; restoring an already-stale initial outline
is not accepted as a successful insertion workflow.

Figure sizing still uses the common export plan. Because paint bounds may
change, even fixed 170 mm width can change the crop origin, scale or height.
Whole-document before/after outputs and graph/coordinate audits must state the
actual plan. No silent coordinate move, auto-migration, installation or deployment
is part of this change. Standard Undo handles document edits; it cannot revert an
application renderer update. A preserved prior candidate remains the rollback.
