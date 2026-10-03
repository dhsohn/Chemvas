# Contract Asset Provenance

These files are a project-scoped snapshot of the factory/machine-observation
contract, used for standalone validation of Chemvas's machine.json output.

## Source

- Repository: https://github.com/dhsohn/machine-contracts
- Commit: 38581a7737cd0521bb3d50b59115eefe3c9254ca
- License: MIT (Copyright (c) 2026 daehyupsohn)

## Scope

This snapshot includes the envelope schema, the semantic validator, and the
payload schemas and registry routes applicable to the `chemvas` producer:

- `chemistry/elementary-step` v1 and v2

Routes and schemas for other producers (orca_auto, ollama_bot, llmdocx) are
excluded. The registry validates chemvas observations identically to the full
upstream registry for all chemvas routes and rejects observations from
unregistered producers.

## Copied files (exact upstream content)

Per-file SHA-256 digests are recorded in `PROVENANCE.json` and verified by
`tests/test_contract_compatibility.py`. The digests were taken from the pin
commit above.

| Local path | Upstream path |
| --- | --- |
| `scripts/validate.py` | `scripts/validate.py` |
| `schemas/machine-observation-v1.schema.json` | `schemas/machine-observation-v1.schema.json` |
| `schemas/payloads/chemistry-elementary-step-v1.schema.json` | `schemas/payloads/chemistry-elementary-step-v1.schema.json` |
| `schemas/payloads/chemistry-elementary-step-v2.schema.json` | `schemas/payloads/chemistry-elementary-step-v2.schema.json` |
| `LICENSE` | `LICENSE` |
| `fixtures/valid/chemvas-*.json` | `fixtures/chemvas-*.json` |

## Derived file

| Local path | Description |
| --- | --- |
| `registry.json` | Project-scoped derivative: chemvas routes and payload contracts only, all upstream `artifact_roles` retained |

## Compatibility

The v1 envelope is frozen per the upstream COMPATIBILITY.md. Interior objects in
the payload schemas are open for producer-side growth. The validator, schemas,
and registry together define the verdict; the JSON Schema alone is strictly
weaker.
