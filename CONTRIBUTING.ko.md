# Chemvas에 기여하기

[English](CONTRIBUTING.md)

Chemvas에 관심을 가져 주셔서 감사합니다! 이 안내는 로컬 환경 설정, 검사 실행
방법, 그리고 무엇보다 이 코드베이스가 따르는 **아키텍처 관례**를 다룹니다. 코드를
옮기기 전에 아키텍처 절을 꼭 읽어 주세요. 모듈 배치는 의도된 것이고 테스트가
강제하므로, 선의의 "정리"라도 CI에서 실패합니다.

참여함으로써 [행동 강령](CODE_OF_CONDUCT.ko.md)을 따르는 데 동의하는 것으로 봅니다.

## 개발 환경 설정

**Python 3.12+**가 필요합니다.

```bash
git clone https://github.com/dhsohn/Chemvas.git
cd Chemvas
python -m venv .venv && source .venv/bin/activate   # optional but recommended
python -m pip install -e ".[dev]"                    # dev tooling
python -m pip install -e ".[dev,rdkit]"              # also enable RDKit features
```

`make check`가 쓰는 공용 `machine.json` 계약 검증기는 별도의 개발 체크아웃입니다.

```bash
git clone https://github.com/dhsohn/machine-contracts.git ~/machine_contracts
```

그 체크아웃이 다른 곳에 있으면 `FACTORY_MACHINE_CONTRACT_REPO`를 설정하세요.
`make check`는 활성화된 가상환경을 먼저 쓰고, 다음으로 저장소의 `.venv`, 마지막으로
`python3`를 씁니다. 인터프리터를 명시하려면 `PYTHON_BIN`을 설정하세요.

개발 트리에서 앱을 실행하려면:

```bash
python app/main.py
```

## 검사 실행

PR을 열기 전에 명령 하나로 기본 로컬 게이트(lint, 포맷, mypy, 전체 테스트 스위트,
`machine.json` 적합성 검사)를 실행합니다.

```bash
make check
```

참고로 개별 게이트는 다음과 같습니다.

```bash
python -m ruff check .     # lint + import sorting
python -m ruff format --check .  # deterministic formatting
python -m mypy             # all production code; migrated owner packages are strict
```

테스트는 PyQt6를 쓰며 `offscreen` 플랫폼 플러그인으로 헤드리스 실행됩니다. 개발
중에는 손댄 파일만 실행하세요.

```bash
QT_QPA_PLATFORM=offscreen python -m pytest tests/test_<area>.py
```

> **테스트 파일마다 별도의 pytest 프로세스를 주세요.** Qt는 테스트 모듈 사이에
> 완전히 초기화되지 않는 전역 애플리케이션 상태를 유지하므로, 한 프로세스에서
> 몰아 돌리면 CI에서는 실패할 테스트가 통과합니다. 이 규칙은
> `scripts/run_test_files.sh` 한 곳에 있습니다. `make check`와 두 CI 잡이 모두 이
> 스크립트를 호출하며, 여러 프로세스를 동시에 돌리되 두 파일을 한 프로세스에 넣는
> 일은 없습니다. 손댄 파일로 범위를 좁히려면 게이트에 파일을 직접 넘기세요.
>
> ```bash
> bash scripts/check.sh tests/test_<area>.py
> ```

새 동작에는 테스트가 따라야 합니다. 대부분의 모듈에는 짝이 되는
`tests/test_<module>.py`가 있습니다.

테스트 모듈 하나는 한 가지 스타일로 유지하세요. 기존 모듈을 확장할 때는 그 파일의
현재 `unittest` 또는 순수 pytest 스타일을 따릅니다. 새로 만드는 독립 테스트
모듈은 순수 pytest 함수를 씁니다. 스타일만 바꾸려고 무관한 테스트를 변환하지 마세요.

CI는 추가로 선택적 RDKit 스모크와 wheel 패키징 스모크를 돌립니다. 이 두
환경 의존 잡은 `make check`에 포함되지 않습니다.

## 아키텍처 관례 (구조를 바꾸기 전에 읽으세요)

규칙 자체는 [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md)가 규범입니다. 평면
`app/chemvas/ui` 패키지의 ports / access / state / service 규율, `core`가
import해도 되는 것, 트랜잭션과 복구 소유권의 분할이 거기 있습니다(한국어판:
[`docs/ARCHITECTURE.ko.md`](docs/ARCHITECTURE.ko.md)). 목표 패키지 경계와 의존
방향은 [`ADR 0001`](docs/adr/0001-feature-oriented-modularization.md)이 정합니다.
코드를 옮기기 전에 둘 다 읽으세요. 아래는 기여자 시점의 요약입니다.

**이 경계는
[`tests/test_architecture_boundaries.py`](tests/test_architecture_boundaries.py)와
[`tests/test_package_dependencies.py`](tests/test_package_dependencies.py)가
강제합니다.** 두 테스트는 AST와 정규식으로 소스를 훑어 금지된 패턴이 다시
나타나면 실패합니다. 이 모듈들을 합치거나 내부에 손을 넣어 "단순화"하려 하면
테스트가 거부합니다.

### 모듈 역할, 예시로 보기

원자 라벨 기능을 예로 들면:

| 접미사 | 역할 | 예 |
| --- | --- | --- |
| `*_ports` | 캔버스나 창에서 서비스/협력자를 해석하는 유일한 정식 경로. | [`canvas_service_ports.py`](app/chemvas/ui/canvas_service_ports.py): `atom_label_service_for_access(canvas)` → `canvas_services_for(canvas).atom_label_service` |
| `*_access` | 호출자 대면 자유 함수. 다른 모듈은 속성을 건드리는 대신 이것을 부른다. | [`atom_label_access.py`](app/chemvas/ui/atom_label_access.py): `add_or_update_atom_label(canvas, atom_id, text)` |
| `*_service` | 실제 구현/로직. 협력자를 **주입된 포트**로 받는다. | `atom_label_service.py` |
| `*_state` | 런타임 상태를 창/캔버스의 private 속성이 아니라 전용 객체에 둔다. | `main_window_state.py` (`MainWindowState`) |
| `*_logic` | 단위 테스트가 쉬운, Qt 없는 순수 헬퍼(파싱, 기하, 레이아웃). | `chemvas.features.annotations` 라벨 레이아웃 API |
| `*_controller` | 캔버스나 창의 한 영역에 대한 상호작용 흐름을 소유하는 조정 클래스(`foo_controller.py`의 `FooController`). 캔버스와 주입된 협력자를 들고 있다. 의도된 예외 하나가 다른 곳에 있다: `ui/hover.py`의 `HoverController`는 hover feature 경계 옆에서 Qt hover 조율을 소유한다(`docs/ARCHITECTURE.md` 참조). | `scene_delete_controller.py` (`SceneDeleteController`) |
| `*_tool` / `*_tools` | `chemvas.ui.tool_base.Tool`을 뿌리로 하는 포인터 도구 계층의 구현. 이 계층의 모든 구현은 `*_tool.py`(도구 하나) 또는 `*_tools.py`(한 계열, `preview_tools.py`처럼 중간 베이스가 있을 수 있음) 모듈에 있다. | `bond_tool.py` (`BondTool`) |
| `*_bundle` | 함께 구성되어 한 필드로 저장·전달되는 서비스 묶음 dataclass. 보통 `build_*` 팩토리 옆에 있다. | `canvas_input_service_bundle.py` (`CanvasInputServiceBundle`) |
| `*_renderer` / `*_rendering` | Qt 페인팅과 그래픽 아이템 그리기 헬퍼: 렌더러 클래스 또는 그리기 함수 모듈. | `bond_renderer.py`, `hover_rendering.py` |

앞의 다섯 행은 주입 포트 규율이며 경계 테스트가 그 대부분을 강제합니다(Qt 없는
`*_logic` 규칙은 저장소 전체 게이트가 아니라 모듈별로 검사). 뒤의 네 행은
코드베이스가 이미 일관되게 쓰는 어휘를 문서화한 것입니다. 새 모듈도 이에 맞추되,
그 접미사를 검사하는 자동 게이트는 없습니다.

런타임의 일부만 필요한 집중 테스트는 더블에 상태나 서비스를 손으로 매달지 말고
그 부분을 실제로 만듭니다.

```python
canvas = SimpleNamespace(
    runtime_state=canvas_runtime_state(graph_state=CanvasGraphState()),
)
```

`tests/runtime_state.canvas_runtime_state(**states)`는 필드 이름을 실제
`CanvasRuntimeState`와 대조하고, `tests/runtime_services.py`는 부분
`CanvasRuntimeServices`에 대해 같은 일을 합니다.

### 경계 테스트가 막는 것

- **private 멤버에 손대지 않기.** 프로덕션 코드에서 `canvas._foo`,
  `getattr(canvas, "_foo")`, `setattr(canvas, "_foo", ...)`를 쓰지 마세요.
- **상태 속성이 아니라 접근자를 거치기.** `canvas.hover_atom_id`,
  `canvas.atom_items`, `canvas.active_bond_order` 같은 캔버스 상태를 직접 읽지
  말고 해당 `*_access` 헬퍼를 쓰세요.
- **서비스는 주입된 포트를 받기.** 서비스는 `window.canvas`, `window.services`,
  `window.canvas_tabs`를 거쳐 들어가면 안 됩니다. 협력자는 전달됩니다
  (`chemvas.bootstrap.main_window_services`의 배선을 보세요). 그래야 서비스마다
  격리해서 테스트할 수 있습니다.
- **`window.canvas` / `window.canvas_tabs`는 shell 표면에서 빠져 있기.**
  `app/chemvas/shell/main_window.py` 밖에서는 캔버스/탭 참조 포트를 쓰세요.
- **제거된 파사드는 제거된 채로.** 경계 테스트에는 `MainWindow`에 다시 넣으면 안
  되는 옛 god-object 메서드 이름이 많이 나열되어 있습니다(예: `set_bond_style`,
  `export_figure`, `bind_active_canvas`). 동작은 적절한 서비스에 추가하세요.

### 기능을 추가하거나 옮기기

1. Qt 없는 도메인 규칙은 `chemvas.domain`에, 기능 조율은 `chemvas.features` 아래
   패키지에 둡니다.
2. 저장소, RDKit, Qt 통합을 위한 작은 기능 소유 프로토콜을 정의합니다. 구체
   구현은 `chemvas.adapters` 아래에 둡니다.
3. 기능 간 동작은 기능 패키지의 공개 API로 노출합니다. 다른 기능의 내부 모듈을
   import하지 마세요.
4. `state.py`, `ports.py`, `service.py`, `qt.py`는 그 역할이 실제 경계일 때만
   만듭니다. 연산 하나에 기본으로 래퍼 사슬이 필요하지는 않습니다.
5. 구체 어댑터는 `chemvas.bootstrap`에서 배선하고 애플리케이션 shell은
   `chemvas.shell` 아래에 둡니다.
6. `tests/test_package_dependencies.py`와
   `tests/test_architecture_boundaries.py`를 둘 다 실행합니다.

레거시 코드를 옮길 때는 기능 전체가 공개 API를 갖추고 해당 레거시 아키텍처 검사를
퇴역시킬 수 있을 때까지 기존 접근 규칙을 유지합니다.

## Pull request

- PR은 집중해서, 논리적 변경 하나에 PR 하나.
- `ruff`, `mypy`, 영향받는 테스트가 로컬에서 통과하는지 확인합니다.
- 동작 변경에는 테스트를 추가하거나 갱신합니다.
- 무엇을 왜 바꿨고 어떻게 검증했는지 적고, 관련 이슈를 링크합니다. PR 템플릿의
  `Motivation` / `Changes` / `Verification` 절이 바로 그 용도입니다.
- 사용자에게 보이는 변경이면 `CHANGELOG.md`의 `## [Unreleased]` 아래를 갱신합니다.

## 버그 신고와 기능 요청

GitHub 이슈 템플릿을 쓰세요. 버그는 OS, Python 버전, RDKit 설치 여부, 재현 단계를
적어 주세요. 그리기 이상은 스크린샷이나 작은 `.chemvas` 파일이 큰 도움이 됩니다.
