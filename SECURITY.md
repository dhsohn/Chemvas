# Security Policy

[한국어](SECURITY.ko.md)

## Supported Versions

Security fixes are released only for the latest minor release on
[PyPI](https://pypi.org/project/chemvas/). Older releases do not receive
backported fixes; upgrade to the latest release to pick up a fix.

| Version | Supported |
| --- | --- |
| 0.21.x | Yes |
| < 0.21 | No |

## Reporting a Vulnerability

Do not report security vulnerabilities through public GitHub issues,
discussions, or pull requests.

Report them privately through GitHub:
[Report a vulnerability](https://github.com/dhsohn/Chemvas/security/advisories/new)
(**Security** tab → **Report a vulnerability**).

Include as much of the following as you can:

- Chemvas version (`chemvas --version` or the **About Chemvas** dialog), Python
  version, operating system, and whether the RDKit extra is installed
- The affected entry point: desktop app, a specific CLI command, or the Python API
- A minimal input file (`.chemvas`, Chemvas SVG, composition/patch/plan JSON,
  or image) and the exact steps or command that trigger the issue
- The observed impact and what you expected instead

## What to Expect

Chemvas is maintained by one person, so the timelines below are targets rather
than guarantees.

- I aim to acknowledge a report within 7 days.
- I will confirm whether the issue is accepted and share a fix plan within
  30 days.
- Accepted issues are fixed in a new release. The fix is published together with
  a GitHub security advisory and a `CHANGELOG.md` entry, and reporters are
  credited unless they ask not to be.

Keep the report private until the fix is released or the advisory is published.

## Scope

Chemvas is a local desktop application and headless CLI. It does not run a
network service. The main security boundary is **untrusted input files**: a
document, SVG, manifest, or image received from someone else should be safe to
open, inspect, render, or process.

In scope:

- Code execution, or reading or writing files other than the requested input
  and output, triggered by opening or processing a crafted file
- Bypass of the documented resource limits (document, image, and CLI input
  byte and pixel limits) that leads to a crash, hang, or memory exhaustion
- CLI commands that modify input files or write outside the requested `--output`
  path, contrary to the contracts in [AGENT_CLI.md](docs/AGENT_CLI.md)
- Exposure of document content through autosave or session recovery files to
  other users on the same machine

Out of scope:

- Vulnerabilities in dependencies such as Qt/PyQt6, RDKit, or Pillow that
  Chemvas does not make worse; report those to the upstream project
- Attacks that require an attacker who already runs code as the same user
- Slow processing of large inputs that stay within the documented limits
- Scientific correctness issues (wrong properties, geometry, or layout); report
  those as regular [issues](https://github.com/dhsohn/Chemvas/issues)
