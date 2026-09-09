from __future__ import annotations

import re
import shutil
import subprocess
import sys
from pathlib import Path
from textwrap import dedent

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "packaging" / "windows" / "chemvas.iss"
ISCC = shutil.which("ISCC") if sys.platform == "win32" else None


def _sections() -> dict[str, list[str]]:
    sections: dict[str, list[str]] = {}
    current = "preprocessor"
    for raw in SCRIPT.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith(";"):
            continue
        if line.startswith("["):
            current = line.removeprefix("[").removesuffix("]")
            assert current not in sections
        else:
            sections.setdefault(current, []).append(line)
    return sections


def _registry_entries() -> list[dict[str, str]]:
    entries = []
    for line in _sections()["Registry"]:
        fields = re.findall(r'(\w+):\s*("(?:[^"]|"")*"|[^;]*)(?:;|$)', line)
        entry = {}
        for name, raw in fields:
            value = raw.strip()
            if value.startswith('"'):
                value = value[1:-1].replace('""', '"')
            entry[name] = value
        assert set(entry) <= {
            "Root",
            "Subkey",
            "ValueType",
            "ValueName",
            "ValueData",
            "Flags",
        }
        entries.append(entry)
    return entries


def test_installer_has_no_extra_mutating_sections() -> None:
    assert set(_sections()) == {
        "preprocessor",
        "Setup",
        "Files",
        "Icons",
        "Registry",
        "Code",
    }


def test_per_user_install_and_platform_contract() -> None:
    settings = dict(line.split("=", 1) for line in _sections()["Setup"])
    assert settings["AppId"] == "Chemvas"
    assert settings["DefaultDirName"] == r"{localappdata}\Programs\Chemvas"
    assert settings["PrivilegesRequired"] == "lowest"
    assert "PrivilegesRequiredOverridesAllowed" not in settings
    assert settings["ArchitecturesAllowed"] == "x64compatible"
    assert settings["ArchitecturesInstallIn64BitMode"] == "x64compatible"
    assert settings["MinVersion"] == "10.0"
    assert settings["ChangesAssociations"] == "yes"
    assert settings["AppVersion"] == settings["VersionInfoVersion"] == "{#AppVersion}"
    assert settings["OutputDir"] == "{#OutputDir}"
    assert settings["OutputBaseFilename"] == "{#InstallerName}"


def test_only_bundle_payload_and_start_menu_shortcut_are_installed() -> None:
    assert _sections()["Files"] == [
        (
            'Source: "{#BundleDir}\\*"; DestDir: "{app}"; '
            "Flags: ignoreversion recursesubdirs createallsubdirs"
        )
    ]
    assert _sections()["Icons"] == [
        'Name: "{userprograms}\\Chemvas\\Chemvas"; Filename: "{app}\\chemvas.exe"'
    ]


def test_registry_targets_exact_owned_keys_and_values() -> None:
    entries = _registry_entries()
    assert all(entry["Root"] == "HKCU" for entry in entries)
    assert all(entry["ValueType"] == "string" for entry in entries)
    expected = {
        (r"Software\Classes\.chemvas\OpenWithProgids", "Chemvas.Document"),
        (r"Software\Classes\Chemvas.Document", ""),
        (r"Software\Classes\Chemvas.Document\DefaultIcon", ""),
        (r"Software\Classes\Chemvas.Document\shell\open\command", ""),
        (r"Software\Classes\Applications\chemvas.exe", "FriendlyAppName"),
        (r"Software\Classes\Applications\chemvas.exe\SupportedTypes", ".chemvas"),
        (r"Software\Classes\Applications\chemvas.exe\shell\open\command", ""),
        (r"Software\Chemvas\Capabilities", "ApplicationName"),
        (r"Software\Chemvas\Capabilities", "ApplicationDescription"),
        (r"Software\Chemvas\Capabilities", "ApplicationIcon"),
        (r"Software\Chemvas\Capabilities\FileAssociations", ".chemvas"),
        (r"Software\RegisteredApplications", "Chemvas"),
    }
    assert len(entries) == len(expected)
    assert {(entry["Subkey"], entry["ValueName"]) for entry in entries} == expected


def test_open_commands_quote_executable_and_document() -> None:
    commands = [
        entry["ValueData"]
        for entry in _registry_entries()
        if entry["Subkey"].endswith(r"\shell\open\command")
    ]
    assert commands == ['"{app}\\chemvas.exe" "%1"'] * 2


def test_uninstall_has_no_unconditional_registry_cleanup_flags() -> None:
    assert all("Flags" not in entry for entry in _registry_entries())


def test_uninstall_code_requires_exact_current_installation_ownership() -> None:
    # Deliberately pin the small Pascal cleanup body, not just a substring that
    # could pass despite a new unconditional delete. Native tests compile it;
    # installation/retarget/uninstallation behavior is a separate Windows check.
    expected = dedent(
        r"""
        function RegistryStringMatches(const Key, ValueName, Expected: String): Boolean;
        var
          Value: String;
        begin
          Result := RegQueryStringValue(HKCU, Key, ValueName, Value) and
            (Value = Expected);
        end;
        procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
        var
          OwnCommand, OwnIcon: String;
        begin
          if CurUninstallStep <> usUninstall then
            Exit;
          OwnCommand := '"' + ExpandConstant('{app}\chemvas.exe') + '" "%1"';
          OwnIcon := '"' + ExpandConstant('{app}\chemvas.exe') + '",0';
          { Another portable installation may have taken over either open command. }
          if RegistryStringMatches(
            'Software\Classes\Chemvas.Document\shell\open\command', '', OwnCommand) then
          begin
            RegDeleteKeyIncludingSubkeys(HKCU, 'Software\Classes\Chemvas.Document');
            if RegistryStringMatches(
              'Software\Classes\.chemvas\OpenWithProgids', 'Chemvas.Document', '') then
              RegDeleteValue(HKCU, 'Software\Classes\.chemvas\OpenWithProgids', 'Chemvas.Document');
          end;
          if RegistryStringMatches(
            'Software\Classes\Applications\chemvas.exe\shell\open\command', '', OwnCommand) then
            RegDeleteKeyIncludingSubkeys(HKCU, 'Software\Classes\Applications\chemvas.exe');
          if RegistryStringMatches(
            'Software\Chemvas\Capabilities', 'ApplicationIcon', OwnIcon) then
          begin
            RegDeleteKeyIncludingSubkeys(HKCU, 'Software\Chemvas\Capabilities');
            if RegistryStringMatches(
              'Software\RegisteredApplications', 'Chemvas', 'Software\Chemvas\Capabilities') then
              RegDeleteValue(HKCU, 'Software\RegisteredApplications', 'Chemvas');
          end;
        end;
        """
    )
    assert _sections()["Code"] == [
        line.strip() for line in expected.splitlines() if line.strip()
    ]


def test_capabilities_match_the_owned_progid() -> None:
    values = {
        (entry["Subkey"], entry["ValueName"]): entry["ValueData"]
        for entry in _registry_entries()
    }
    assert values[(r"Software\RegisteredApplications", "Chemvas")] == (
        r"Software\Chemvas\Capabilities"
    )
    assert values[(r"Software\Chemvas\Capabilities\FileAssociations", ".chemvas")] == (
        "Chemvas.Document"
    )


@pytest.mark.parametrize("name", ["BundleDir", "AppVersion", "OutputDir"])
def test_required_definitions_have_no_silent_defaults(name: str) -> None:
    preprocessor = "\n".join(_sections()["preprocessor"])
    assert f"#ifndef {name}\n#error {name} " in preprocessor
    assert f'#if Trim({name}) == ""\n#error {name} must not be empty.\n#endif' in (
        preprocessor
    )
    assert f"#define {name} " not in preprocessor


@pytest.mark.skipif(ISCC is None, reason="Native Windows ISCC compiler is not on PATH")
@pytest.mark.parametrize(
    "fault",
    [
        None,
        "BundleDir",
        "AppVersion",
        "OutputDir",
        "empty",
        "missing_exe",
        "existing_output",
    ],
)
def test_native_compiler_accepts_bundle_and_rejects_invalid_inputs(
    tmp_path: Path, fault: str | None
) -> None:
    """Compile only: never execute an installer or change the registry."""
    bundle = tmp_path / "bundle space 한글"
    output = tmp_path / "output space 한글"
    bundle.mkdir()
    output.mkdir()
    if fault != "missing_exe":
        (bundle / "chemvas.exe").write_bytes(b"synthetic compiler input, not executed")
    target = output / "Chemvas-1.2.3-windows-x64-setup.exe"
    if fault == "existing_output":
        target.write_bytes(b"preserve existing output")
    definitions = {
        "BundleDir": str(bundle),
        "AppVersion": "1.2.3",
        "OutputDir": str(output),
    }
    if fault in definitions:
        del definitions[fault]
    if fault == "empty":
        definitions["OutputDir"] = ""
    assert ISCC is not None
    result = subprocess.run(
        [
            ISCC,
            "/Q",
            *(f"/D{key}={value}" for key, value in definitions.items()),
            str(SCRIPT),
        ],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    if fault is None:
        assert result.returncode == 0, result.stdout + result.stderr
        assert target.read_bytes().startswith(b"MZ")
    else:
        assert result.returncode != 0
        expected = {
            "empty": "OutputDir must not be empty",
            "missing_exe": "BundleDir must contain chemvas.exe",
            "existing_output": "Refusing to overwrite an existing installer",
        }.get(fault, f"{fault} must")
        assert expected in result.stdout + result.stderr
        if fault == "existing_output":
            assert target.read_bytes() == b"preserve existing output"
        else:
            assert not target.exists()
