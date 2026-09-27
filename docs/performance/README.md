# Editor transaction baseline

Run from the repository root:

```sh
QT_QPA_PLATFORM=offscreen PYTHONPATH=app .venv/bin/python scripts/benchmark_editor.py --atoms 100 1000 --repeats 3 > baseline.json
```

The script creates a fresh real canvas for every sample. Carbon chains contain
at most 50 atoms per row. Move translates the entire selection by (10, 5), delete
removes it, and paste adds 10 unbonded nitrogen atoms. Each operation warms up once
per document size. Undo and Redo must restore the exact document snapshots or the
script fails. JSON includes environment, sample range, median and savepoint counts.

The timer covers the synchronous edit/history call, including its savepoint and
scene work. Document creation, selection setup, garbage collection and validation
are outside the timer. A mock wrapper counts savepoint captures; its call overhead
is included. Deferred painting, pointer events, disk I/O, images and session
recovery are outside this benchmark. Use the same machine, Qt platform and fixture
sizes for comparisons; this is not an application-wide latency measurement.

## Initial observation

[Raw results](editor-2026-09-27.json), measured on 2026-09-27 with Darwin arm64,
Python 3.13.14, Qt 6.11.0, offscreen; three samples after warmup. Source base:
`c1ebf2b971da55b2049de48364e35e20f94a5438` plus the local history/delete/graph
simplification patch. These are baseline observations, not a before/after speedup.

| Operation | 100 atoms, median ms | 1,000 atoms, median ms |
| --- | ---: | ---: |
| Move | 17.905 | 180.020 |
| Move Undo | 18.075 | 182.422 |
| Move Redo | 18.114 | 182.611 |
| Delete | 9.975 | 159.763 |
| Delete Undo | 4.394 | 41.960 |
| Delete Redo | 7.588 | 134.002 |
| Paste 10 atoms | 7.095 | 61.875 |
| Paste Undo | 7.040 | 58.780 |
| Paste Redo | 6.354 | 58.350 |

Every measured operation captured exactly one document savepoint. The normal test
suite checks that bound and exact Undo/Redo restoration at two document sizes in
`test_selection_update_performance.py`. Wall-clock numbers are deliberately not
CI thresholds: hardware load and platform differences require comparable runs.
A capture count above one should trigger investigation of nested transactions.

## Fixed-size edits in larger documents

Separate the document size from the amount changed:

```sh
QT_QPA_PLATFORM=offscreen PYTHONPATH=app .venv/bin/python scripts/benchmark_editor.py --atoms 100 1000 --edited-atoms 10 --paste-atoms 10 --repeats 5 > small-edits.json
```

`--edited-atoms` selects the first N atom IDs for move/delete and the initial
selection for paste. It must fit every document size. Without it the original
whole-document selection is retained. `--paste-atoms` controls only the inserted
nitrogen count. `--operations paste` runs only paste and its Undo/Redo. The JSON
reports both initial and selected atom counts; selection setup is checked before
timing. Deleting atoms also deletes their incident bonds and invisible orphaned
endpoints according to the editor's normal rules.

The following measurements were taken on 2026-09-28, on the same Darwin arm64,
Python 3.13.14, Qt 6.11.0 offscreen host, with five samples after one warmup.
The source was `9729c3738dbe889c6adf0bddc11c7a514677e016` plus the local
annotation-state, style-history and mapping-owner changes. The second run also
included per-savepoint sharing of primitive graphics captures. Both runs keep
10 atoms selected and paste 10 atoms. Timing runs were separate from the focused
tests.

| Operation | 100 atoms before, ms | 100 atoms shared capture, ms | 1,000 atoms before, ms | 1,000 atoms shared capture, ms |
| --- | ---: | ---: | ---: | ---: |
| Move 10 | 6.680 | 5.473 | 58.782 | 45.679 |
| Delete 10 | 6.183 | 4.978 | 59.427 | 46.198 |
| Paste 10 | 7.227 | 5.929 | 62.632 | 46.955 |
| Paste Undo | 7.130 | 5.329 | 63.434 | 46.095 |
| Paste Redo | 6.424 | 4.918 | 61.885 | 45.990 |

[Before timings](editor-small-edits-2026-09-28.json) and
[shared-capture timings](editor-small-edits-shared-capture-2026-09-28.json)
include every sample range and the remaining Undo/Redo operations. All measured
calls capture one document savepoint and restore the exact document on Undo/Redo.
These synchronous calls are faster by roughly 17–27% in this run, but still scale
with total document size. This is not a claim about interactive frame rate or
saving the document.

### Where the time goes

A separate cProfile run of the 1,000-atom paste attributed 212.395 ms of
218.738 ms to `DocumentSavepoint.capture`. The profiler makes these times much
larger than the unprofiled medians. Use them to locate work, not as latency figures.
`BondPrimitiveGraphicsSnapshot.capture` ran 3,963 times, because the exact
scene-item snapshot and the runtime bond/atom snapshots independently read the
same primitives. Their cumulative times overlap and must not be added.

The change shares primitive capture results through a dictionary allocated inside
each `DocumentSavepoint.capture`. Every consumer asks for the same complete
primitive state; move scopes only control which items are included. No capture
results survive for reuse by the next savepoint. In the follow-up profile, the
1,000-atom paste reads 1,983 primitives instead of 3,963. Scene membership, object identity,
model/container snapshots, restoration order and rollback verification remain
unchanged. The full document snapshot is still taken for paste.

[Before profile](editor-small-edits-profile-2026-09-28.json) and
[shared-capture profile](editor-small-edits-shared-capture-profile-2026-09-28.json)
record the top 35 cumulative entries for paste, Undo and Redo separately.
The new regression checks full and scoped captures, one primitive read per item,
shared snapshot identity, fresh values in the next capture and restoration of the
same Qt item. Disabling the sharing makes its capture-count assertion fail.

To profile the three calls separately without including document setup or snapshot
validation, run this from the repository root:

```sh
QT_QPA_PLATFORM=offscreen PYTHONPATH=app .venv/bin/python - <<'PY'
import cProfile
from PyQt6.QtWidgets import QApplication
from scripts import benchmark_editor as benchmark

app = QApplication([])
app.setQuitOnLastWindowClosed(False)
state = benchmark.document_state(1000)
benchmark.exercise(app, state, "paste", edited_atoms=10, paste_atoms=10)
measure = benchmark.measure
phases = iter(("paste", "paste-undo", "paste-redo"))
def profile_call(action):
    profile = cProfile.Profile()
    result = measure(lambda: profile.runcall(action))
    profile.dump_stats(next(phases) + ".prof")
    return result
benchmark.measure = profile_call
benchmark.exercise(app, state, "paste", edited_atoms=10, paste_atoms=10)
PY
```

Inspect a file with `python -m pstats paste.prof`, then use `sort cumulative`
and `stats 35`. Further reductions should be driven by these measured costs;
restricting rollback to the pasted atoms would require proving that selection,
existing geometry, groups and all failure callbacks cannot change other items.
