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
