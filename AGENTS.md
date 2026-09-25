# 작업자 진입점 — Chemvas

공장 공통 규칙은 `~/manual/AGENTS.md`가 지정하는 순서를 따른다(`FACTORY_MANUAL.md` →
자기 사이트 장부 → 이 파일). 여기에는 그 규칙을 복제하지 않고, **이 레포에만 해당하는
운영 사실**만 둔다.

## 이 레포가 무엇인가

PyQt6 기반 2D 화학 구조 드로잉 데스크톱 앱이자 오픈소스 연구 소프트웨어(MIT, PyPI
`chemvas`)다. 개발·검증·커밋·PR은 macOS, Windows(네이티브·WSL), Linux 어디서든
진행할 수 있으며, 특정 호스트의 체크아웃을 개발 정본으로 지정하지 않는다.
사용자가 지정한 저장소와 작업 위치를 우선하고, 별도 지정이 없으면 현재 작업 환경에서
진행한다. 다른 호스트에 체크아웃이 있다는 이유로 작업 위치를 바꾸지 않는다.
변경의 기준은 Git 저장소와 작업 브랜치이며, 검증 결과에는 실제 실행 플랫폼과 범위를
명시한다.

## 검증

```bash
make check
```

Ruff·format·mypy를 돌린 뒤 **테스트를 `test_*.py` 파일마다 별도 pytest 프로세스로**
실행한다. Linux/WSL·macOS의 공통 검사는 offscreen이며, macOS의 메뉴·포커스 workflow
두 파일은 Cocoa로 직렬 실행한다. Windows는 제품과 같은 Windows Qt 백엔드를 쓰고
창 포커스 충돌을 막도록 전체를 직렬 실행한다. 실제 Python의 OS에 따라 범위를 선택하고
범위·skip 사유를 출력한다.
Linux/WSL의 비 UTF-8 바이트 파일명 검사는 다른 OS에서 제외하고, 경로 별칭·대화상자
표시 차이는 공통 테스트에서 처리한다. Windows는 Git Bash에서 같은 게이트를 실행하며
`.venv/Scripts/python.exe`도 자동 선택한다. `PYTHON_BIN`·활성 `VIRTUAL_ENV`가 없으면 체크아웃의
`.venv`를 쓰고, 없으면 `requires-python`(3.12+)을 만족하는 인터프리터를 `PATH`와 일반 설치
위치에서 찾아 만든 뒤 `[dev]` extras를 설치한다(`pyproject.toml`이 바뀌면 재설치). 그래서 새
worktree에서도 준비 없이 돌고, 맞는 인터프리터가 없거나 `.venv`가 낮은 버전으로 만들어졌으면
시스템 Python으로 대체하지 않고 시도 목록과 함께 실패한다. 심볼릭 링크 `.venv`(다른 체크아웃의 환경)는
지우거나 설치하지 않고 거부한다. 테스트는 `PYTHONPATH=app`으로 설치본이
아닌 이 체크아웃의 코드를 쓴다. Qt가 모듈 간에 완전히 리셋되지 않는 전역 상태를 유지하므로, 전체를
한 프로세스에 몰아넣은 실행은 통과해도 CI를 대표하지 않는다 — 이 루프가 게이트다.
`machine.json` 적합성 검증은 게이트가 `~/machine_contracts`의 정본 validator를 직접
연결한다(`FACTORY_MACHINE_CONTRACT_REPO`로 위치 변경 가능). 해당 테스트를 직접 돌릴
때도 validator 경로가 없으면 검증 없이 성공하지 않고 실패한다. 만진 파일만 좁혀 돌리려면:

```bash
bash scripts/check.sh tests/test_<area>.py
```

## 고치기 전에 읽을 것

| 무엇을 만지는가 | 원본 |
| --- | --- |
| 모듈 경계·리팩터링·테스트 관례 | [CONTRIBUTING.md](CONTRIBUTING.md) 및 [ADR 0005](docs/adr/0005-responsibility-based-editor-boundaries.md) — 구조 변경 전 필독. 구조 검사는 소유권과 의존 경계 계약을 보호한다 |
| 설계 결정 기록 — 공개 계약·메이저 버전·기능 제거·상태 소유권 이동·외부 동작 의존은 같은 PR에 ADR을 쓴다 | [ADR 안내](docs/adr/README.md) |
| 릴리스 절차 | [RELEASING.md](RELEASING.md) |
| `machine.json` 공통 봉투 | `~/machine_contracts`의 `COMPATIBILITY.md`(v1 동결) |

`machine.json` 표면을 바꾸려면 `machine-contracts`에 먼저 랜딩·릴리스하고, 이 레포 CI의
pin(`.github/workflows/ci.yml`의 `ref:`)을 의도적으로 전진시킨다.

## `make check`가 흡수하지 못하는 것

- **RDKit·wheel 스모크는 CI 전용이다.** 선택적 RDKit 백엔드와 휠 패키징이 걸린 변경은
  CI의 `rdkit-smoke`·`package-smoke` 잡이 판정한다.
- **GUI 실검증은 별도다.** Mac 게이트의 Cocoa workflow는 메뉴·포커스 범위를 검증한다.
  offscreen 스위트나 이 제한된 Cocoa 검사가 모든 실제 창·입력기 상호작용을 증명하지는
  않는다 — 캔버스가 걸린 변경은 해당 기능의 실캔버스 확인을 따로 한다.
- **사용자 문서(`.chemvas`)는 실물이다.** 라이브 확인에 쓴 문서에 테스트 잔여물이 남지
  않았는지 되돌려 확인한다.
