"""Validate project-local contract assets and emitter conformance.

The validator, schemas, and registry under contracts/machine-observation/ are a
project-scoped snapshot of the upstream machine-contracts repository.  These
tests prove they accept valid chemvas observations, reject invalid ones with
the same semantics as the upstream validator, and work standalone without any
external clone or environment variable.
"""

from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[1]
CONTRACT_ROOT = ROOT / "contracts" / "machine-observation"

_spec = importlib.util.spec_from_file_location(
    "contract_validate",
    CONTRACT_ROOT / "scripts" / "validate.py",
)
assert _spec is not None and _spec.loader is not None
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)

ContractError = _mod.ContractError
REQUIREMENT_OPERATORS = _mod.REQUIREMENT_OPERATORS
validate_document = _mod.validate_document
validate_machine_path = _mod.validate_machine_path
validate_path = _mod.validate_path


def _fixture(name: str) -> dict[str, Any]:
    text = (CONTRACT_ROOT / "fixtures" / "valid" / name).read_text(encoding="utf-8")
    return json.loads(text)


# --- Valid fixtures ---


class TestValidFixtures:
    def test_all_valid_fixtures_conform(self) -> None:
        fixtures = sorted((CONTRACT_ROOT / "fixtures" / "valid").glob("*.json"))
        assert len(fixtures) >= 4
        for fixture in fixtures:
            validate_path(fixture)

    def test_v1_ready(self) -> None:
        validate_document(_fixture("chemvas-ready.json"))

    def test_v1_blocked(self) -> None:
        validate_document(_fixture("chemvas-blocked.json"))

    def test_v2_ready(self) -> None:
        validate_document(_fixture("chemvas-v2-ready.json"))

    def test_v2_blocked(self) -> None:
        validate_document(_fixture("chemvas-v2-blocked.json"))


# --- Registry scope ---


class TestRegistry:
    @pytest.fixture()
    def registry(self) -> dict[str, Any]:
        return json.loads((CONTRACT_ROOT / "registry.json").read_text(encoding="utf-8"))

    def test_contains_only_chemvas_producer(self, registry: dict[str, Any]) -> None:
        assert registry["producers"] == ["chemvas"]

    def test_routes_only_reference_chemvas(self, registry: dict[str, Any]) -> None:
        assert all(r["producer"] == "chemvas" for r in registry["routes"])

    def test_payload_keys_match_schemas(self, registry: dict[str, Any]) -> None:
        for payload in registry["payload_contracts"]:
            schema = json.loads(
                (CONTRACT_ROOT / payload["schema"]).read_text(encoding="utf-8")
            )
            assert payload["required_keys"] == schema["required"]

    def test_producers_agree_with_routes(self, registry: dict[str, Any]) -> None:
        route_producers = {r["producer"] for r in registry["routes"]}
        assert route_producers == set(registry["producers"])

    def test_operation_kinds_agree_with_routes(self, registry: dict[str, Any]) -> None:
        route_ops = {r["operation_kind"] for r in registry["routes"]}
        assert route_ops == set(registry["operation_kinds"])

    def test_requirements_use_implemented_operators(
        self, registry: dict[str, Any]
    ) -> None:
        for payload in registry["payload_contracts"]:
            for req in payload.get("ready_requirements", []):
                assert req["operator"] in REQUIREMENT_OPERATORS
                if req["operator"] == "equals":
                    assert "value" in req
        for route in registry["routes"]:
            for req in route.get("requirements", []):
                assert req["operator"] in REQUIREMENT_OPERATORS
                if req["operator"] == "equals":
                    assert "value" in req

    def test_unimplemented_operator_rejected(self) -> None:
        check_requirements = _mod._check_requirements
        with pytest.raises(ContractError, match="unimplemented operator"):
            check_requirements(
                {"step_id": "S01"},
                [{"path": ["step_id"], "operator": "bogus"}],
                location="test",
            )

    def test_routes_are_unique(self, registry: dict[str, Any]) -> None:
        keys = [
            (
                r["producer"],
                r["operation_kind"],
                r["payload_contract"],
                r["payload_version"],
            )
            for r in registry["routes"]
        ]
        assert len(keys) == len(set(keys))

    def test_payload_contracts_reachable_from_routes(
        self, registry: dict[str, Any]
    ) -> None:
        registered = [(p["name"], p["version"]) for p in registry["payload_contracts"]]
        assert len(registered) == len(set(registered))
        routed = {
            (r["payload_contract"], r["payload_version"]) for r in registry["routes"]
        }
        assert sorted(set(registered)) == sorted(routed)


# --- Route/producer rejections ---


class TestRouteRejections:
    def test_unregistered_producer_is_rejected(self) -> None:
        doc = _fixture("chemvas-ready.json")
        doc["producer"]["name"] = "orca_auto"
        with pytest.raises(ContractError, match="route"):
            validate_document(doc)

    def test_v1_payload_on_v2_route(self) -> None:
        doc = _fixture("chemvas-ready.json")
        doc["payload"]["contract"]["version"] = 2
        with pytest.raises(ContractError, match="endpoint_pair"):
            validate_document(doc)

    def test_v2_payload_on_v1_route(self) -> None:
        doc = _fixture("chemvas-v2-ready.json")
        doc["payload"]["contract"]["version"] = 1
        with pytest.raises(ContractError, match="endpoint_geometry"):
            validate_document(doc)

    def test_unregistered_payload_contract_name(self) -> None:
        doc = _fixture("chemvas-ready.json")
        doc["payload"]["contract"]["name"] = "chemistry/results-bundle"
        with pytest.raises(ContractError, match="not registered"):
            validate_document(doc)

    def test_incompatible_producer_operation(self) -> None:
        doc = _fixture("chemvas-ready.json")
        doc["operation"]["kind"] = "chemistry/orca-run"
        with pytest.raises(ContractError, match="route"):
            validate_document(doc)


# --- Schema rejections ---


class TestSchemaRejections:
    def test_missing_required_payload_key(self) -> None:
        doc = _fixture("chemvas-v2-blocked.json")
        doc["payload"]["data"].pop("endpoint_geometry")
        with pytest.raises(ContractError, match="endpoint_geometry"):
            validate_document(doc)

    def test_extra_payload_key(self) -> None:
        doc = _fixture("chemvas-ready.json")
        doc["payload"]["data"]["unknown_field"] = "extra"
        with pytest.raises(ContractError, match="unknown_field"):
            validate_document(doc)

    def test_wrong_type_in_payload(self) -> None:
        doc = _fixture("chemvas-ready.json")
        doc["payload"]["data"]["step_id"] = 42
        with pytest.raises(ContractError, match="step_id"):
            validate_document(doc)

    def test_missing_required_envelope_key(self) -> None:
        doc = _fixture("chemvas-ready.json")
        doc.pop("lineage")
        with pytest.raises(ContractError):
            validate_document(doc)

    def test_extra_envelope_key(self) -> None:
        doc = _fixture("chemvas-ready.json")
        doc["extra_field"] = "not allowed"
        with pytest.raises(ContractError):
            validate_document(doc)


# --- Ready predicate rejections ---


class TestReadyPredicates:
    def test_v2_ready_requires_non_null_endpoint_geometry(self) -> None:
        doc = _fixture("chemvas-v2-ready.json")
        doc["payload"]["data"]["endpoint_geometry"] = None
        with pytest.raises(ContractError, match="endpoint_geometry"):
            validate_document(doc)

    def test_v1_ready_requires_non_null_endpoint_pair(self) -> None:
        doc = _fixture("chemvas-ready.json")
        doc["payload"]["data"]["endpoint_pair"] = None
        with pytest.raises(ContractError, match="endpoint_pair"):
            validate_document(doc)

    def test_v2_endpoint_geometry_key_required(self) -> None:
        doc = _fixture("chemvas-v2-blocked.json")
        validate_document(doc)
        doc["payload"]["data"].pop("endpoint_geometry")
        with pytest.raises(ContractError, match="endpoint_geometry"):
            validate_document(doc)


# --- Semantic rejections ---


class TestSemanticRejections:
    def test_finished_pending_handoff(self) -> None:
        doc = _fixture("chemvas-ready.json")
        doc["handoff"]["status"] = "pending"
        with pytest.raises(ContractError, match="pending"):
            validate_document(doc)

    def test_finished_pending_delivery(self) -> None:
        doc = _fixture("chemvas-ready.json")
        doc["delivery"]["status"] = "pending"
        with pytest.raises(ContractError):
            validate_document(doc)

    def test_non_succeeded_cannot_be_ready(self) -> None:
        doc = _fixture("chemvas-ready.json")
        doc["lifecycle"]["outcome"] = "failed"
        with pytest.raises(ContractError):
            validate_document(doc)

    def test_ready_requires_payload(self) -> None:
        doc = _fixture("chemvas-ready.json")
        doc["payload"] = None
        with pytest.raises(ContractError):
            validate_document(doc)

    def test_complete_delivery_with_missing_required_artifact(self) -> None:
        doc = copy.deepcopy(_fixture("chemvas-blocked.json"))
        doc["artifacts"]["mandatory"] = {
            "status": "missing",
            "required": True,
            "role": "document",
            "path": None,
            "media_type": None,
            "bytes": None,
            "byte_sha256": None,
        }
        doc["delivery"]["status"] = "complete"
        with pytest.raises(ContractError, match="unavailable required artifact"):
            validate_document(doc)

    def test_incomplete_delivery_with_all_available(self) -> None:
        doc = _fixture("chemvas-blocked.json")
        doc["delivery"]["status"] = "incomplete"
        with pytest.raises(ContractError, match="incomplete delivery needs"):
            validate_document(doc)

    def test_blocked_accepts_null_payload(self) -> None:
        doc = copy.deepcopy(_fixture("chemvas-blocked.json"))
        doc["payload"] = None
        doc["handoff"]["status"] = "blocked"
        validate_document(doc)

    def test_duplicate_lineage_entries(self) -> None:
        doc = _fixture("chemvas-ready.json")
        entry = {
            "producer": {"name": "upstream", "version": "1.0"},
            "operation_id": "op-1",
            "byte_sha256": "a" * 64,
        }
        doc["lineage"]["upstream"] = [entry, entry]
        with pytest.raises(ContractError, match="duplicate"):
            validate_document(doc)


# --- Duplicate JSON keys ---


class TestDuplicateKeys:
    def test_duplicate_json_keys_are_rejected(self, tmp_path: Path) -> None:
        raw = (CONTRACT_ROOT / "fixtures" / "valid" / "chemvas-ready.json").read_text(
            encoding="utf-8"
        )
        raw = raw.replace(
            '"step_id": "S01"',
            '"step_id": "S01", "step_id": "duplicate"',
        )
        path = tmp_path / "duplicate-keys.json"
        path.write_text(raw, encoding="utf-8")
        with pytest.raises(ContractError, match="duplicate JSON key"):
            validate_path(path)


# --- Machine-path validation (artifact bytes, basename, path traversal) ---


class TestMachineValidation:
    def test_machine_basename_required(self, tmp_path: Path) -> None:
        doc = _fixture("chemvas-ready.json")
        path = tmp_path / "observation.json"
        path.write_text(json.dumps(doc), encoding="utf-8")
        with pytest.raises(ContractError, match="basename"):
            validate_machine_path(path)

    def test_artifact_byte_verification(self, tmp_path: Path) -> None:
        doc = copy.deepcopy(_fixture("chemvas-ready.json"))
        content = b"test artifact content\n"
        doc["artifacts"]["test-artifact"] = {
            "status": "available",
            "required": True,
            "role": "document",
            "path": "test.txt",
            "media_type": "text/plain",
            "bytes": len(content),
            "byte_sha256": hashlib.sha256(content).hexdigest(),
        }
        (tmp_path / "test.txt").write_bytes(content)
        machine = tmp_path / "machine.json"
        machine.write_text(json.dumps(doc), encoding="utf-8")
        validate_machine_path(machine)

        (tmp_path / "test.txt").write_bytes(b"corrupted\n")
        with pytest.raises(ContractError, match="byte count|sha256"):
            validate_machine_path(machine)

    def test_artifact_missing_file(self, tmp_path: Path) -> None:
        doc = copy.deepcopy(_fixture("chemvas-ready.json"))
        doc["artifacts"]["missing-art"] = {
            "status": "available",
            "required": True,
            "role": "document",
            "path": "does-not-exist.txt",
            "media_type": "text/plain",
            "bytes": 10,
            "byte_sha256": "a" * 64,
        }
        machine = tmp_path / "machine.json"
        machine.write_text(json.dumps(doc), encoding="utf-8")
        with pytest.raises(ContractError, match="missing"):
            validate_machine_path(machine)

    def test_artifact_path_traversal_schema_rejected(self, tmp_path: Path) -> None:
        doc = copy.deepcopy(_fixture("chemvas-ready.json"))
        doc["artifacts"]["escape"] = {
            "status": "available",
            "required": True,
            "role": "document",
            "path": "../../../etc/passwd",
            "media_type": "text/plain",
            "bytes": 100,
            "byte_sha256": "a" * 64,
        }
        machine = tmp_path / "machine.json"
        machine.write_text(json.dumps(doc), encoding="utf-8")
        with pytest.raises(ContractError, match="not valid"):
            validate_machine_path(machine)

    @pytest.mark.skipif(
        sys.platform == "win32",
        reason="os.symlink requires SeCreateSymbolicLinkPrivilege on Windows",
    )
    def test_artifact_symlink_escapes_generation(self, tmp_path: Path) -> None:
        generation = tmp_path / "gen"
        generation.mkdir()
        outside = tmp_path / "outside"
        outside.mkdir()
        secret = outside / "secret.txt"
        secret.write_bytes(b"secret content\n")
        link = generation / "escape.txt"
        link.symlink_to(secret)
        content = secret.read_bytes()
        doc = copy.deepcopy(_fixture("chemvas-ready.json"))
        doc["artifacts"]["escape"] = {
            "status": "available",
            "required": True,
            "role": "document",
            "path": "escape.txt",
            "media_type": "text/plain",
            "bytes": len(content),
            "byte_sha256": hashlib.sha256(content).hexdigest(),
        }
        machine = generation / "machine.json"
        machine.write_text(json.dumps(doc), encoding="utf-8")
        with pytest.raises(
            ContractError, match="escapes the generation|another volume"
        ):
            validate_machine_path(machine)

    def test_artifact_hash_mismatch(self, tmp_path: Path) -> None:
        doc = copy.deepcopy(_fixture("chemvas-ready.json"))
        content = b"correct content\n"
        doc["artifacts"]["hash-test"] = {
            "status": "available",
            "required": True,
            "role": "document",
            "path": "hashfile.txt",
            "media_type": "text/plain",
            "bytes": len(content),
            "byte_sha256": "b" * 64,
        }
        (tmp_path / "hashfile.txt").write_bytes(content)
        machine = tmp_path / "machine.json"
        machine.write_text(json.dumps(doc), encoding="utf-8")
        with pytest.raises(ContractError, match="sha256"):
            validate_machine_path(machine)

    def test_artifact_size_mismatch(self, tmp_path: Path) -> None:
        doc = copy.deepcopy(_fixture("chemvas-ready.json"))
        content = b"short\n"
        doc["artifacts"]["size-test"] = {
            "status": "available",
            "required": True,
            "role": "document",
            "path": "sizefile.txt",
            "media_type": "text/plain",
            "bytes": 9999,
            "byte_sha256": hashlib.sha256(content).hexdigest(),
        }
        (tmp_path / "sizefile.txt").write_bytes(content)
        machine = tmp_path / "machine.json"
        machine.write_text(json.dumps(doc), encoding="utf-8")
        with pytest.raises(ContractError, match="byte count"):
            validate_machine_path(machine)


# --- Provenance ---


class TestProvenance:
    PIN_HASHES: dict[str, str] = {
        "scripts/validate.py": "ec9eda23eb908939afddad0f58ffe18e8e6c54b10a8b3d2f3f2e65de269759e1",
        "schemas/machine-observation-v1.schema.json": "deda0ca05d46a68382b20a43601a1ddc2826d6f15a62b8b6273c672d39f8de1b",
        "schemas/payloads/chemistry-elementary-step-v1.schema.json": "a0390f2cbe19cdca6b3909e21fd36ac3148e8604ba10acf55148cc9f56155923",
        "schemas/payloads/chemistry-elementary-step-v2.schema.json": "9a696aa280e83922604da2ec3fdca8d2af1140a43ba4598b83e338bf3c03cc84",
        "LICENSE": "25a57a182f456e94b38019bc404e069e86e28b3c4a0196e6498e4f5c7ae03382",
        "fixtures/valid/chemvas-ready.json": "96c950f71d476f607a182b742598e15a46501155f36ab812c49cd660cee2fb48",
        "fixtures/valid/chemvas-blocked.json": "326ad7e99257685fc3ac473c16080d7254c5441023385b4280796812deb9b0d7",
        "fixtures/valid/chemvas-v2-ready.json": "2922c6586257e9c010bd6060353e45867f2c9d243897e46af91c655508672d72",
        "fixtures/valid/chemvas-v2-blocked.json": "f843224418d2ad9a0730c874f4f7532c095f472859a4459dd7b57e9bd8375caa",
    }
    REGISTRY_HASH = "720ecf05c8400a9d7809e2c65297a4d513e5766e6014f608143fb875f8157769"

    @staticmethod
    def _file_sha256(path: Path) -> str:
        return hashlib.sha256(path.read_bytes()).hexdigest()

    def test_copied_files_match_pin_hashes(self) -> None:
        for relative, expected in self.PIN_HASHES.items():
            local = CONTRACT_ROOT / relative
            assert local.is_file(), f"missing: {relative}"
            actual = self._file_sha256(local)
            assert actual == expected, f"{relative}: expected {expected}, got {actual}"

    def test_derived_registry_hash(self) -> None:
        actual = self._file_sha256(CONTRACT_ROOT / "registry.json")
        assert actual == self.REGISTRY_HASH

    def test_provenance_json_records_all_hashes(self) -> None:
        prov = json.loads(
            (CONTRACT_ROOT / "PROVENANCE.json").read_text(encoding="utf-8")
        )
        assert prov["pin"] == "38581a7737cd0521bb3d50b59115eefe3c9254ca"
        for relative, expected in self.PIN_HASHES.items():
            assert prov["copied_files"][relative]["sha256"] == expected
        assert prov["derived_files"]["registry.json"]["sha256"] == self.REGISTRY_HASH

    def test_notice_records_pin_sha(self) -> None:
        notice = (CONTRACT_ROOT / "NOTICE.md").read_text(encoding="utf-8")
        assert "38581a7737cd0521bb3d50b59115eefe3c9254ca" in notice

    def test_gitattributes_preserves_contract_bytes(self) -> None:
        attrs = (ROOT / ".gitattributes").read_text(encoding="utf-8")
        assert "contracts/machine-observation/** -text" in attrs

    def test_license_is_mit(self) -> None:
        text = (CONTRACT_ROOT / "LICENSE").read_text(encoding="utf-8")
        assert "MIT License" in text
        assert "daehyupsohn" in text

    def test_all_registered_schemas_exist(self) -> None:
        registry = json.loads(
            (CONTRACT_ROOT / "registry.json").read_text(encoding="utf-8")
        )
        assert (
            CONTRACT_ROOT / "schemas" / "machine-observation-v1.schema.json"
        ).is_file()
        for payload in registry["payload_contracts"]:
            assert (CONTRACT_ROOT / payload["schema"]).is_file()


# --- Standalone: no external paths required ---


class TestStandalone:
    def test_validator_cli_accepts_valid_fixture(self, tmp_path: Path) -> None:
        doc = _fixture("chemvas-ready.json")
        path = tmp_path / "valid.json"
        path.write_text(json.dumps(doc), encoding="utf-8")
        env = {k: v for k, v in os.environ.items() if "FACTORY" not in k.upper()}
        result = subprocess.run(
            [sys.executable, str(CONTRACT_ROOT / "scripts" / "validate.py"), str(path)],
            capture_output=True,
            text=True,
            env=env,
        )
        assert result.returncode == 0, result.stderr

    def test_validator_cli_rejects_invalid(self, tmp_path: Path) -> None:
        doc = _fixture("chemvas-ready.json")
        doc["producer"]["name"] = "unknown_producer"
        path = tmp_path / "invalid.json"
        path.write_text(json.dumps(doc), encoding="utf-8")
        env = {k: v for k, v in os.environ.items() if "FACTORY" not in k.upper()}
        result = subprocess.run(
            [sys.executable, str(CONTRACT_ROOT / "scripts" / "validate.py"), str(path)],
            capture_output=True,
            text=True,
            env=env,
        )
        assert result.returncode == 1

    def test_gate_uses_local_validator_path(self) -> None:
        script = (ROOT / "scripts" / "check.sh").read_text(encoding="utf-8")
        assert "contracts/machine-observation/scripts/validate.py" in script
        assert "FACTORY_MACHINE_CONTRACT_REPO" not in script

    def test_no_external_clone_in_ci(self) -> None:
        ci = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
        assert "repository: dhsohn/machine-contracts" not in ci

    def test_no_external_clone_in_platform_ci(self) -> None:
        platform = (ROOT / ".github" / "workflows" / "platform.yml").read_text(
            encoding="utf-8"
        )
        assert "repository: dhsohn/machine-contracts" not in platform

    def test_gate_validator_path_is_project_local(self) -> None:
        script = (ROOT / "scripts" / "check.sh").read_text(encoding="utf-8")
        validator_line = [
            line
            for line in script.splitlines()
            if "CONTRACT_VALIDATOR=" in line and "export" not in line
        ]
        assert validator_line
        assert "HOME" not in validator_line[0]
        assert "FACTORY" not in validator_line[0]

    def test_hostile_env_variable_ignored(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from tests.calculation_workflow_support import _validate_common_machine

        pass_all = tmp_path / "pass_all.py"
        pass_all.write_text("import sys; sys.exit(0)\n", encoding="utf-8")
        monkeypatch.setenv("FACTORY_MACHINE_CONTRACT_VALIDATOR", str(pass_all))

        valid_doc = _fixture("chemvas-ready.json")
        generation = tmp_path / "valid-gen"
        generation.mkdir()
        (generation / "machine.json").write_text(
            json.dumps(valid_doc), encoding="utf-8"
        )
        _validate_common_machine(generation / "machine.json")

        invalid_doc = _fixture("chemvas-ready.json")
        invalid_doc["producer"]["name"] = "unknown_producer"
        bad_gen = tmp_path / "bad-gen"
        bad_gen.mkdir()
        (bad_gen / "machine.json").write_text(json.dumps(invalid_doc), encoding="utf-8")
        with pytest.raises(subprocess.CalledProcessError):
            _validate_common_machine(bad_gen / "machine.json")
