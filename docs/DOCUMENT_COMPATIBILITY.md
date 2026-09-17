# Document compatibility

[한국어](DOCUMENT_COMPATIBILITY.ko.md)

## Product promise

Future Chemvas updates must continue to open currently supported, valid **v7
`.chemvas` documents**, keeping their stored drawing and document information
editable. Users must not need an old installation just to recover a supported
drawing. This is a supported file contract, not a temporary migration window.

The baseline is the v7 contract supported on 2026-09-13, including
optional mark colors, mirrored equilibrium arrows, crossed `double_either` bonds,
images, groups, perspective coordinates, and Calculation Plan v2. Existing v7
files without optional fields remain supported too. Some older Chemvas releases
used the same version number before those additions and cannot read all of them;
this promise does not retroactively change those installed readers.

Opening a document does not rewrite its source file. Explicit saving may use the
current output format and normalize its representation, but must preserve the
supported stored information. Keeping the original or using Save As is useful
when sharing with an older installation.

## Format changes

- The application release number and document format number are independent.
  The current writer still emits **v7**; this policy introduces no new format.
- A serialized change that an existing reader cannot correctly interpret needs
  a new document format version. This includes new fields rejected by the
  existing strict schema, new enum values, and changes to a field's meaning.
  Do not add another incompatible feature under the v7 label. From v8 on, the
  revision rule in "Next format version" below decides whether such a change
  takes a new revision or a new version; under v7 every one of them takes a
  new version.
- A future writer version must not remove v7 from the readable versions. Version
  interpretation belongs at the document boundary, not in every GUI or CLI
  consumer. Implement any necessary conversion there when an actual new format
  is introduced; do not add speculative migrations or capability negotiation.
- Before a format change ships, verify opening supported old fixtures and
  preserving their information through editing, saving and reopening. Audit
  outputs that currently retain their input version, including Graph Patch:
  never label newly introduced information as v7 or silently discard it to fit.
- Unknown versions, unknown fields, malformed documents and invalid references
  remain errors. Do not guess their meaning, silently omit unsupported content,
  or bypass validation to make a file appear to open successfully.

## Next format version

Version 7 is frozen as the contract supported on 2026-09-13; it carries no
revision number, and nothing more is added under its label. Several additions
were made under the v7 label before that date, so a reader older than one of
them rejects a newer v7 file as an invalid document even though both say
`"version": 7`. The file cannot say which reader it needs. The wrapper's key set
is closed, so that information cannot be added to v7 either: it arrives with the
next format version.

The next format version, v8, extends the wrapper to exactly these keys (the
release number is illustrative; the writer fills the real one):

```json
{
  "type": "chemvas",
  "version": 8,
  "schema": 1,
  "min_reader": "0.17.0",
  "state": {}
}
```

- `version` is the format generation, as today. It is the unit of the reading
  promise: a reader that supports a generation reads every revision of it that
  it knows, and a writer version never drops a supported generation.
- `schema` is the revision within a generation. It starts at 1 and increases by
  one for an **additive** change: one where every document valid under the
  previous revision is still valid, with the same meaning, under the new one.
  A new optional field, a new enumeration value or a new optional collection
  is additive; the strict reader of an older revision still rejects such a
  document, which is exactly what the revision number explains. A **breaking**
  change — a required field, a changed meaning, a removed or renamed field, a
  wrapper change — is one where some previously valid document is no longer
  valid or means something else; it needs a new generation, which resets the
  revision to 1. The test is validity and meaning of existing documents, not
  whether an old reader rejects the new one.
- `min_reader` is the lowest Chemvas release that reads this revision in full.
  The writer fills it from a table in the code keyed by `(version, schema)`;
  it is never typed by hand, and the implementation must carry a test that
  keeps the table and the writer in step.

A reader judges a document in this order and reports the first failure:

1. An unknown `version` is refused with the message used today, naming the
   generations this release reads.
2. The wrapper is validated for that generation, independently of the
   revision: for v7 exactly `type`, `version` and `state` as today; for v8
   exactly the keys above, with the right `type`, an integer `schema` of at
   least 1, a release string in `min_reader` and an object in `state`. A
   document that fails here is an invalid document, never a newer one.
3. A known `version` whose `schema` is above the highest revision this release
   knows is refused as a **newer document, not an invalid one**: the message
   names the document's format and revision, the highest revision this release
   reads, and the release from `min_reader` that can open it. The reader
   decides by `schema`; `min_reader` is only quoted, never trusted.
4. A known revision is validated as strictly as today. An unknown field, an
   unknown enumeration value or an invalid reference remains an error. The
   revision number explains a refusal; it does not relax validation.

`inspect-document` will report the same three values under `document_format`,
so an agent can compare a file with the release its user has installed before
handing it over.

Introducing v8 follows the rules above: keep reading v7, convert at the
document boundary, verify the frozen v7 fixtures, and freeze a v8 fixture set
separately. Until a real change to the document requires v8, none of this is
implemented; this section is the requirement it will be built to.

## Scope and limits

This promise covers native document reading, including a v7 document embedded in
an editable Chemvas SVG. Clipboard payloads, CLI requests/reports, SVG wrapper
metadata and calculation handoff artifacts have their own versioned contracts;
a native document change does not automatically change those versions.

It does not add support for pre-v7 documents, guarantee that old applications can
open newly saved formats, or promise byte-identical JSON or pixel-identical text
across fonts and platforms. Opening a saved calculation plan preserves its data;
it does not guarantee that a future chemistry backend will reproduce its results
or that an incomplete or stale plan is ready to execute. Scientific validation
remains separate from document readability. Correctness and security fixes may
still reject malformed inputs that an earlier implementation accidentally accepted.

Calculation data a document carries is preserved on the same terms as its
drawing, whether or not the optional RDKit backend is installed: Chemvas never
drops a plan because it cannot compute with it. Chemvas does not record
whether the drawing has changed since a plan was written; what it checks is
whether the plan still fits the drawing it is saved with, and three existing
surfaces report the result without discarding data on their own: document
validation refuses a plan that references an atom or bond that no longer
exists; the desktop asks before saving a plan whose components, declared
charges or mapped atoms no longer agree with the drawing, keeping it as an
invalid draft when its references still resolve and, only with the user's
consent, leaving it out of the file when they do not; and `inspect-plan`
reports whether each step is ready. An edit that leaves those facts intact,
such as a changed bond order, passes every check, and whether the plan still
describes the intended chemistry remains the user's judgement. Preserve the
data, and say what is known to need review; that is the rule for every
extension a document carries.

## Regression baseline

[`tests/fixtures/document-v7`](../tests/fixtures/document-v7) contains fixed,
synthetic examples, not user research data. The files keep a literal version `7`
and must not be regenerated from the current writer when the format evolves.
They are representative witnesses, not an exhaustive specification of every
valid v7 document; the domain validation tests remain necessary.

[`test_document_compatibility.py`](../tests/test_document_compatibility.py) checks
native I/O, editable SVG and CLI preservation.
[`test_document_edit_roundtrip.py`](../tests/test_document_edit_roundtrip.py)
checks the desktop editing and save/reopen path. Both run under `make check`.
Tests for unsupported history pin versions 1–6 rather than treating every version
below the current writer as unsupported. Updating the writer constant alone must
not invalidate the v7 reading baseline.
