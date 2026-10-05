# 작업자 진입점 — Chemvas

공장 작업자는 `~/manual/AGENTS.md`가 지정하는 순서를 따른다(`FACTORY_MANUAL.md` →
자기 사이트 장부 → 이 파일). 일반 기여자는 이 레포만으로 개발·검증할 수 있으며
[CONTRIBUTING.md](CONTRIBUTING.md)가 안내한다. 여기에는 공장 규칙을 복제하지 않고,
**이 레포에만 해당하는 운영 사실**만 둔다.

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

매 검사에서 줄·분기 커버리지를 수집하고 새 `htmlcov/check.*/`에 HTML·JSON·텍스트
보고서를 남긴다. 완료 보고에는 두 수치와 실행 플랫폼·전체/선별 범위·RDKit 포함 여부를
적는다. 선별 검사 수치를 전체 기준선으로 보고하지 않는다. CI의 공통·RDKit 잡도 각자의
범위를 표시한 요약과 보고서 artifact를 남긴다.

Ruff·format·mypy를 돌린 뒤 **테스트를 `test_*.py` 파일마다 별도 pytest 프로세스로**
실행한다. 모든 OS의 공통 검사는 offscreen으로 여러 파일을 동시에 돌린다. 엄격한 시간
제한을 검사하는 ring-correspondence 파일은 다른 파일이 끝난 뒤 단독 실행한다. 그 안의
`latency` 검사는 계측 부하 없이 기존 시간 제한을 판정하며 커버리지에는 합산하지 않는다. 호스트의
네이티브 백엔드가 필요한 파일만 `scripts/check.sh`의 목록대로 직렬 실행한다: macOS의
메뉴·포커스·문서 편집·복구 workflow 네 파일은 Cocoa로, Windows에서 그린 글리프를 재는 파일은
제품과 같은 글꼴 엔진을 쓰는 Windows Qt 백엔드로 돌린다. Mac 테스트는 수집 전에
프로세스 내부의 휘발성 설정으로 AppKit 창 복원을 끄므로 Python의 이전 충돌 복원 창이
검사를 막지 않는다. 사용자 환경설정이나 저장된 복구 파일은 변경하지 않는다. Windows offscreen에서
글꼴 측정 때문에 실패하는 새 테스트 파일은 이 목록에 넣는다. 실제 Python의 OS에 따라
범위를 선택하고 범위·skip 사유를 출력한다. CI는 `main` push와 PR 커밋마다 한 번씩
돈다. 실행을 취소하면 그 커밋에 취소된 필수 체크가 남아 머지가 막히므로, 앞선 실행은
취소하지 않고 끝까지 둔다. PR CI는 Linux에서만 게이트를 돌리고, macOS·Windows 공통
검사는 수동 실행 워크플로 `Platform tests`로 릴리스 전에 돌린다(RELEASING.md).
macOS 변경은 로컬 `make check`로도 확인한다.
Linux/WSL의 비 UTF-8 바이트 파일명 검사는 다른 OS에서 제외하고, 경로 별칭·대화상자
표시 차이는 공통 테스트에서 처리한다. Windows는 Git Bash에서 같은 게이트를 실행하며
`.venv/Scripts/python.exe`도 자동 선택한다. `PYTHON_BIN`·활성 `VIRTUAL_ENV`가 없으면 체크아웃의
`.venv`를 쓰고, 없으면 `requires-python`(3.12+)을 만족하는 인터프리터를 `PATH`와 일반 설치
위치에서 찾아 만든 뒤 `[dev]` extras를 설치한다(`pyproject.toml`이 바뀌면 재설치). 그래서 새
worktree에서도 준비 없이 돌고, 맞는 인터프리터가 없거나 `.venv`가 낮은 버전으로 만들어졌으면
시스템 Python으로 대체하지 않고 시도 목록과 함께 실패한다. 심볼릭 링크 `.venv`(다른 체크아웃의 환경)는
지우거나 설치하지 않고 거부한다. `uv venv`로 만든 것처럼 pip이 없는 `.venv`도 거부하므로
`.venv`를 지우거나 `PYTHON_BIN`을 지정한다. 테스트는 `PYTHONPATH=app`으로 설치본이
아닌 이 체크아웃의 코드를 쓴다. Qt가 모듈 간에 완전히 리셋되지 않는 전역 상태를 유지하므로, 전체를
한 프로세스에 몰아넣은 실행은 통과해도 CI를 대표하지 않는다 — 이 루프가 게이트다.
`make check`는 `machine.json` 적합성 검증을 하지 않는다. 그 스냅샷과 화학 provider는
제거되었다. 만진 파일만 좁혀 돌리려면:

```bash
bash scripts/check.sh tests/test_<area>.py
```

입력·포커스·저장·복구 변경의 작은 네이티브 확인은 `make check-native`로 실행한다.
macOS와 네이티브 Windows에서만 지원하며, 기존 편집·텍스트·복구 테스트를 호스트
백엔드에서 파일별 직렬 실행한다. 전체 릴리스 플랫폼 게이트를 대체하지 않는다.

## 고치기 전에 읽을 것

| 무엇을 만지는가 | 원본 |
| --- | --- |
| 모듈 경계·리팩터링·테스트 관례 | [CONTRIBUTING.md](CONTRIBUTING.md) 및 [ADR 0005](docs/adr/0005-responsibility-based-editor-boundaries.md) — 구조 변경 전 필독. 구조 검사는 소유권과 의존 경계 계약을 보호한다 |
| 설계 결정 기록 — 공개 계약·메이저 버전·기능 제거·상태 소유권 이동·외부 동작 의존은 같은 PR에 ADR을 쓴다 | [ADR 안내](docs/adr/README.md) |
| 릴리스 절차 | [RELEASING.md](RELEASING.md) |
| 제거된 화학 provider | [ADR 0035](docs/adr/0035-retire-rdkit-chemistry-provider.md). 이 저장소는 `machine.json`을 쓰지 않고 provider 채택·core 버전·실행 승인을 기록하지 않는다 |

## `make check`가 흡수하지 못하는 것

- **휠 스모크는 CI 전용이다.** 패키징이 걸린 변경은 CI의 `package-smoke` 잡이 판정한다.
  RDKit 잡과 `rdkit` extra는 없다.
- **GUI 실검증은 별도다.** Mac 게이트의 Cocoa workflow는 메뉴·포커스·문서 편집·복구 범위를 검증한다.
  offscreen 스위트나 이 제한된 Cocoa 검사가 모든 실제 창·입력기 상호작용을 증명하지는
  않는다 — 캔버스가 걸린 변경은 해당 기능의 실캔버스 확인을 따로 한다.
- **사용자 문서(`.chemvas`)는 실물이다.** 라이브 확인에 쓴 문서에 테스트 잔여물이 남지
  않았는지 되돌려 확인한다.
