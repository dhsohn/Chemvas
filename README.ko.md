<p align="center">
  <img src="https://raw.githubusercontent.com/dhsohn/Chemvas/main/docs/images/banner.png" alt="Chemvas — 2D 화학 구조 드로잉 캔버스" width="680">
</p>

<p align="center">
  <a href="https://github.com/dhsohn/Chemvas/actions/workflows/ci.yml"><img src="https://github.com/dhsohn/Chemvas/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
  <a href="https://pypi.org/project/chemvas/"><img src="https://img.shields.io/pypi/v/chemvas" alt="PyPI"></a>
  <a href="https://www.python.org/"><img src="https://img.shields.io/badge/python-3.12%2B-blue.svg" alt="Python 3.12+"></a>
  <a href="https://github.com/dhsohn/Chemvas/blob/main/LICENSE"><img src="https://img.shields.io/badge/License-MIT-blue.svg" alt="License: MIT"></a>
</p>

<p align="center"><a href="https://github.com/dhsohn/Chemvas/blob/main/README.md">English</a> · <b>한국어</b></p>

Chemvas는 **2D 화학 구조와 반응 스킴을 그리는** 가벼운 PyQt6 앱입니다 —
ACS 1996 기본 스타일, ChemDraw 호환 단축키, 논문에 바로 쓰는 figure export까지.
빠르게 그리고, 정확하게 내보냅니다.

![Chemvas — C–P 결합 절단 반응 스킴(KOtBu / THF)을 그린 캔버스](https://raw.githubusercontent.com/dhsohn/Chemvas/main/docs/images/demo.png)

## 왜 필요한가

실험 노트나 논문에 넣을 스킴 하나를 그리는 데 상용 제품이 필요해서는 안 되고,
편집 자동화가 LLM에게 그림을 통째로 맡기는 일이 되어서도 안 됩니다. Chemvas는
인터랙티브 캔버스를 작고 빠르게 유지하면서 렌더·검사·편집·계산 handoff를
headless CLI 계약으로 노출합니다 — 문서 편집은 원본 hash에 결속되고, 지원하지
않는 입력은 fail closed합니다. agent는 제안하고, 검증이 결정합니다.

## 빠른 시작

```bash
pip install chemvas              # 기본 (PyQt6 포함 설치)
pip install "chemvas[rdkit]"     # + SMILES import, 분자식/분자량, 계산 handoff, 3D
chemvas
```

툴바에서 도구를 고르고 캔버스에 클릭/드래그로 그립니다. SMILES 문자열을 입력하고
**Insert**를 누르면 미리보기 후 클릭 위치에 배치됩니다 *(RDKit)*.
**File ▸ Open**으로 [examples/template2.chemvas](https://github.com/dhsohn/Chemvas/blob/main/examples/template2.chemvas)를
열면 위 스크린샷의 문서를 볼 수 있습니다.

## 무엇을 하나

| 기능 | 용도 | 상세 |
|---|---|---|
| **드로잉** | 결합·링·화살표·bracket·원자 라벨 — ChemDraw 호환 단축키 지원 | [REFERENCE](https://github.com/dhsohn/Chemvas/blob/main/docs/REFERENCE.md) |
| **Figure export** | plain SVG / PDF / PNG / TIFF, 글리프 아웃라인, 결정론적 물리 크기 | [REFERENCE](https://github.com/dhsohn/Chemvas/blob/main/docs/REFERENCE.md#figure-export) |
| **화학 I/O** | SMILES import, `.mol` 상호운용, 2D→3D `.xyz`, Molecule Info *(RDKit)* | [REFERENCE](https://github.com/dhsohn/Chemvas/blob/main/docs/REFERENCE.md#chemistry-io) |
| **Agent CLI** | headless 문서 구성 / 레이아웃 점검 / 렌더 / 검사 / hash-gated Graph Patch, Qt 창 없음 | [AGENT_CLI](https://github.com/dhsohn/Chemvas/blob/main/docs/AGENT_CLI.md) |
| **계산 handoff** | elementary step, 검토된 precomplex, step당 `machine.json` 하나 *(RDKit)* | [AGENT_CLI](https://github.com/dhsohn/Chemvas/blob/main/docs/AGENT_CLI.md#calculation-states-and-elementary-steps) |

문서는 `.chemvas` 파일(JSON, version 7 계약)이며 자동저장·크래시 복구를
지원합니다. *(RDKit)* 표시가 붙은 기능 외에는 모두 RDKit 없이 동작합니다.

## 개발·테스트·전체 문서

- `make check`가 로컬 게이트 전체를 실행합니다 — lint, 포맷, mypy,
  파일 단위로 격리된 headless 테스트 스위트, `machine.json` 적합성 검사.
  구조를 옮기기 전에 [CONTRIBUTING.md](https://github.com/dhsohn/Chemvas/blob/main/CONTRIBUTING.md)를 먼저 읽으세요 —
  아키텍처 경계는 테스트로 강제됩니다.
- 문서 색인: [REFERENCE](https://github.com/dhsohn/Chemvas/blob/main/docs/REFERENCE.md) · [AGENT_CLI](https://github.com/dhsohn/Chemvas/blob/main/docs/AGENT_CLI.md) ·
  [ARCHITECTURE](https://github.com/dhsohn/Chemvas/blob/main/docs/ARCHITECTURE.ko.md) · [CHANGELOG](https://github.com/dhsohn/Chemvas/blob/main/CHANGELOG.md) ·
  [RELEASING](https://github.com/dhsohn/Chemvas/blob/main/RELEASING.md)
- 알려진 빈칸(SDF 상호운용, 단일 파일 바이너리, 다중 분자 3D export) →
  [로드맵](https://github.com/dhsohn/Chemvas/blob/main/docs/REFERENCE.md#roadmap--not-yet-supported)

## License

[MIT License](https://github.com/dhsohn/Chemvas/blob/main/LICENSE)
