# Chemvas에 기여하기

[English](CONTRIBUTING.md)

Chemvas에 관심을 가져 주셔서 감사합니다! 이 가이드는 로컬 개발 환경 구축, 검사 실행 방법, 그리고 코드베이스가 준수하는 **아키텍처 규칙**을 안내합니다.

모듈 구조 변경 전에 아키텍처 규칙을 꼭 확인해 주세요. 패키지 간의 경계는 자동화된 테스트를 통해 엄격하게 검증됩니다.

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

자세한 아키텍처 설계는 [`docs/ARCHITECTURE.ko.md`](docs/ARCHITECTURE.ko.md) (영문: [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md)) 및 [`ADR 0001`](docs/adr/0001-feature-oriented-modularization.md)에 기술되어 있습니다.

패키지 경계 규칙은 [`tests/test_architecture_boundaries.py`](tests/test_architecture_boundaries.py) 및 [`tests/test_package_dependencies.py`](tests/test_package_dependencies.py)에 의해 강제됩니다.

### 모듈 역할 및 접미사 규칙

| 접미사 | 역할 | 예시 |
| --- | --- | --- |
| `*_ports` | 캔버스 또는 창에서 서비스/협력자를 조회하는 단일 표준 진입점 | [`canvas_service_ports.py`](app/chemvas/ui/canvas_service_ports.py) |
| `*_access` | 호출자용 함수 인터페이스; 모듈은 상태 속성을 직접 읽는 대신 이 함수를 호출 | [`atom_label_access.py`](app/chemvas/ui/atom_label_access.py) |
| `*_service` | 비즈니스 로직 구현체; 주입된 포트를 통해 협력자를 전달받음 | `atom_label_service.py` |
| `*_state` | 런타임 상태 데이터클래스; 위젯에 직접 속성을 두는 것을 방지 | `main_window_state.py` |
| `*_logic` | Qt 의존성이 없는 순수 함수 (파싱, 기하 계산 등) | `chemvas.features.annotations` |
| `*_controller` | 특정 기능 영역의 상호작용 흐름을 조율하는 클래스 | `scene_delete_controller.py` |
| `*_tool` | `chemvas.ui.tool_base.Tool`을 상속하는 포인터 도구 구현체 | `bond_tool.py` |
| `*_bundle` | 함께 생성되어 전달되는 서비스들을 묶은 데이터클래스 | `canvas_input_service_bundle.py` |
| `*_renderer` | Qt 페인팅 및 그래픽 아이템 그리기 헬퍼 | `bond_renderer.py` |

테스트 작성 시 필요한 런타임 상태만 부분적으로 구성할 수 있습니다:

```python
canvas = SimpleNamespace(
    runtime_state=canvas_runtime_state(graph_state=CanvasGraphState()),
)
```

### 핵심 아키텍처 제약

- **비공개 멤버 직접 접근 금지**: `canvas._foo`와 같은 내부 멤버에 직접 접근하지 않습니다.
- **액세서 함수 사용**: 상태 속성을 직접 읽지 않고 `*_access` 헬퍼를 통해 접근합니다.
- **의존성 주입**: 전역 싱글턴에 의존하지 않고 생성자 인자나 포트를 통해 협력자를 주입받습니다.
- **기능 패키지화**: 순수 도메인 로직은 `chemvas.domain`, 사용자 기능 조율은 `chemvas.features`에 배치합니다.

## 풀 리퀘스트 (PR)

- 하나의 논리적 변경 사항 단위로 PR을 작성합니다.
- 로컬에서 `make check`가 오류 없이 통과하는지 확인합니다.
- 새로운 기능이나 버그 수정 시 관련 회귀 테스트를 반드시 추가합니다.
- PR 템플릿의 항목에 따라 변경 동기와 검증 방법을 상세히 작성합니다.
- 사용자에게 영향을 주는 변경 사항은 `CHANGELOG.md`의 `## [Unreleased]` 항목에 기록합니다.

## 버그 제보 및 기능 제안

GitHub 이슈 템플릿을 사용하여 등록해 주세요. 버그 제보 시 OS, Python 버전, RDKit 설치 여부 및 재현 단계를 포함해 주시면 해결에 큰 도움이 됩니다.
