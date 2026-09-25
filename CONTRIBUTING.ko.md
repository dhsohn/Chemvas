# Chemvas에 기여하기

[English](CONTRIBUTING.md)

이 가이드는 로컬 개발 환경 구축, 검사 실행 방법, 그리고 코드베이스가 준수하는 **아키텍처 규칙**을 안내합니다.

모듈 구조 변경 전에 아키텍처 규칙을 확인합니다. 패키지 간의 경계는 자동화된 테스트를 통해 엄격하게 검증됩니다.

모든 기여자는 [행동 강령](CODE_OF_CONDUCT.ko.md)을 준수해야 합니다.

## 개발 환경 설정

**Python 3.12+**가 필요합니다.

macOS, Linux, Windows(네이티브 및 WSL) 환경에서 개발하고 검증할 수 있습니다.

```bash
git clone https://github.com/dhsohn/Chemvas.git
cd Chemvas
python -m venv .venv && source .venv/bin/activate   # optional but recommended
python -m pip install -e ".[dev]"                    # dev tooling
python -m pip install -e ".[dev,rdkit]"              # also enable RDKit features
```

전체 검증 게이트를 실행하려면 공용 `machine.json` 계약 검증기가 필요합니다:

```bash
git clone https://github.com/dhsohn/machine-contracts.git ~/machine_contracts
```

다른 경로에 클론한 경우 `FACTORY_MACHINE_CONTRACT_REPO` 환경변수에 해당 경로를 설정하세요.

소스 코드에서 앱을 실행하려면:

```bash
python app/main.py
```

## 검사 실행

PR을 제출하기 전 다음 단일 명령어로 기본 로컬 게이트(린트, 포맷, mypy, 전체 테스트, 계약 검증)를 실행합니다:

```bash
make check
```

게이트는 사전 준비가 필요 없으므로 새로 클론한 저장소나 `git worktree`에서도 그대로 실행됩니다. `PYTHON_BIN`이나 활성화된 가상 환경(`VIRTUAL_ENV`)이 인터프리터를 지정하지 않으면 체크아웃 자체의 `.venv`를 사용합니다. `.venv`가 없으면 처음 발견한 Python 3.12 이상(`PATH`, 그다음 `/usr/local/bin`, `/opt/homebrew/bin`, `~/.local/bin`, conda의 `bin` 같은 일반 설치 위치)으로 만들고 `dev` extras를 설치하며, `pyproject.toml`이 바뀌면 다시 설치합니다. 더 낮은 버전의 Python으로 대신 실행하지는 않습니다. 조건에 맞는 인터프리터가 없거나 기존 `.venv`가 그런 Python으로 만들어졌다면, 시도한 인터프리터를 알리고 중단합니다. 다른 체크아웃의 환경에 설치하지 않도록 심볼릭 링크인 `.venv`도 거부합니다. RDKit은 설치하지 않으므로 RDKit 테스트는 로컬에서 skip되고 CI의 RDKit 잡에서 실행됩니다.

개별 검사 도구는 다음과 같이 수동 실행할 수 있습니다:

```bash
python -m ruff check .     # lint + import sorting
python -m ruff format --check .  # deterministic formatting
python -m mypy             # all production code; migrated owner packages are strict
```

수정한 파일과 관련된 테스트만 실행하려면:

```bash
bash scripts/check.sh tests/test_<area>.py
```

> **프로세스 격리 원칙**: Qt는 전역 상태를 유지하므로 서로 다른 테스트 모듈이 한 프로세스에서 실행되면 비정상적인 결과가 발생할 수 있습니다. 테스트는 항상 프로세스 격리를 보장하는 `scripts/check.sh` 또는 `scripts/run_test_files.sh`를 통해 실행하세요:
>
> ```bash
> bash scripts/check.sh tests/test_<area>.py
> ```

## 아키텍처 규칙

현재 규칙은 [ADR 0005](docs/adr/0005-responsibility-based-editor-boundaries.md)에 기록되어 있습니다. [`docs/ARCHITECTURE.ko.md`](docs/ARCHITECTURE.ko.md)는 실제 구현과 경계를 설명합니다.

### 책임을 기준으로 구성하기

- 기능 단위 구현은 응집도 있게 유지합니다. 명확한 별도 책임, 의존성 경계, 독립적인 재사용 필요가 있을 때만 모듈을 분리합니다. `state`, `access`, `ports`, `service`, `bundle` 접미사 계층을 기계적으로 분리하지 않습니다.
- 캔버스 범위의 협력 객체는 직접 주입하여 메서드를 호출합니다. 컨트롤러와 도구는 자신이 소유한 공개 상태와 Qt API를 직접 사용할 수 있습니다. 접근자나 프로토콜은 활성 문서 확인, 표현 변환, 히스토리 연산 제한 등 실질적인 경계 처리에만 사용하며, 단순 위임(forwarding) 목적의 래퍼는 생성하지 않습니다.
- 상태와 변경 규칙은 단일 소유자(single owner)가 관리합니다. 다른 모듈은 해당 소유자의 공개 인터페이스를 통해 작업하며, 중복 상태 유지, 비공개 멤버 접근, 트랜잭션·무효화·수명 주기 우회를 금지합니다.
- 동적으로 변경되는 의존성(예: 활성 문서, 교체 가능한 모델)은 사용 시점에 조회하며, 수명 주기 이후까지 참조를 유지하지 않습니다.
- 문서 데이터 모델, 검증, 화학 도메인 규칙은 `domain` 및 `core`에서 Qt와 완전 분리하여 유지합니다. 데스크톱 UI 및 렌더링 구현(`ui`, `shell`, `adapters`, 데스크톱 기능 모듈)은 Qt 및 어댑터를 직접 사용할 수 있습니다. 헤드리스 기능 API의 비-GUI 계약과 RDKit 선택적 사용은 유지합니다.
- 패키지 간 호출은 공개 API를 사용하며, 즉시 실행(eager) import 순환을 금지합니다.

### 경계 검토와 테스트

구조 변경 시에는 이동하는 책임, 최종 소유자, 제거되는 간접 조회 단계를 명시합니다. 변경 시 파악해야 할 코드 복잡도와 간접 참조를 최소화하는 것을 원칙으로 합니다.

아키텍처 테스트는 의존 방향, 단일 소유권, 복구 계약을 검증합니다. 전달 헬퍼의 목록이나 기계적인 접근자 존재를 강제하지 않습니다. 합리적인 단순화를 가로막는 기존 구조 테스트는 계약 보존 하에 함께 개정합니다. 신규 경계 테스트는 정상 케이스와 위반 주입 케이스를 함께 검증합니다.

편집 기능 수정 시 취소, Undo/Redo, 편집 실패 복구, 문서 저장/불러오기 워크플로가 유지되어야 합니다. 배선(wiring) 전용 단언을 제거할 때도 실제 동작 검증(workflow) 테스트는 유지합니다. 관련 검사는 [`tests/test_architecture_boundaries.py`](tests/test_architecture_boundaries.py), [`tests/test_package_dependencies.py`](tests/test_package_dependencies.py) 및 기능별 워크플로 테스트에 위치합니다.

## 풀 리퀘스트 (PR)

- 하나의 논리적 변경 사항 단위로 PR을 작성합니다.
- 로컬에서 `make check`가 오류 없이 통과하는지 확인합니다.
- 새로운 기능이나 버그 수정 시 관련 회귀 테스트를 반드시 추가합니다.
- PR 템플릿의 항목에 따라 변경 동기와 검증 방법을 상세히 작성합니다.
- 사용자에게 영향을 주는 변경 사항은 `CHANGELOG.md`의 `## [Unreleased]` 항목에 기록합니다.

## 버그 제보 및 기능 제안

GitHub 이슈 템플릿을 사용하여 등록합니다. 버그 제보 시 OS, Python 버전, RDKit 설치 여부 및 재현 단계를 포함합니다.
