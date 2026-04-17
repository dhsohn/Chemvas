# Refactoring / Test Coverage Report

작성일: 2026-04-17

## 1. 현재 상태 요약

- 실행 기준: `pytest --cov=app --cov-report=term-missing`
- 결과: `398 passed in 10.85s`
- 전체 커버리지: `71%`

전체 숫자만 보면 나쁘지 않지만, 실제 리스크는 소수의 대형 오케스트레이션 모듈에 집중되어 있다. 반대로 순수 로직 모듈은 이미 잘 분리되어 있고 테스트 품질도 높은 편이다. 특히 `ui/template_insert_logic.py`, `ui/smiles_insert_logic.py`, `ui/selection_hit_logic.py`, `core/template_geometry.py`, `core/history.py`는 앞으로의 분리 작업에서 기준점으로 삼기 좋다.

## 2. 우선 점검 대상

| 영역 | 규모 / 커버리지 | 근거 | 판단 |
| --- | --- | --- | --- |
| `app/ui/canvas_view.py` | `7367` lines / `58%` | 함수 `481`개, 컨트롤러를 들고 있으면서도 여전히 핵심 상태 변경을 직접 수행 | 최우선 리팩토링 대상 |
| `app/core/tools.py` | `1209` lines / `60%` | 툴 클래스 `20`개, 입력 lifecycle과 preview 처리 패턴이 반복 | 상위 우선순위 |
| `app/ui/scene_ops_controller.py` | `759` lines / `65%` | 삭제/플립/클립보드/히스토리 조합이 한 클래스에 혼재 | 상위 우선순위 |
| `app/ui/insert_controller.py` | `492` lines / `61%` | 순수 계획 로직은 분리됐지만 scene mutation/history 조합이 남아 있음 | 상위 우선순위 |
| `app/ui/main_window.py` | `2214` lines / `78%` | `_init_toolbars()` 369 lines, `_apply_theme()` 323 lines | 중간 우선순위 |
| `app/core/rdkit_conversion.py` | `464` lines / `86%` | alias/stereo/multi-component 분기 복잡도 높음 | 선택적 고위험 분기 보강 필요 |
| `app/core/rdkit_adapter.py` | `83%` | helper pass-through wrapper가 많고 일부 wrapper는 사실상 미사용처럼 보임 | API 표면 정리 필요 |

## 3. 리팩토링 권장 사항

### 3.1 `CanvasView`를 "Qt 어댑터 + 오케스트레이터" 이상으로 키우지 않기

핵심 문제는 이미 컨트롤러를 도입했는데도 `CanvasView`가 여전히 너무 많은 도메인 책임을 직접 들고 있다는 점이다.

- 대표 함수
  - `insert_structure_model()` at `app/ui/canvas_view.py:868`
  - `begin_selection_3d_rotation()` at `app/ui/canvas_view.py:4231`
  - `_merge_overlapping_atoms()` at `app/ui/canvas_view.py:6070`
  - `add_or_update_atom_label()` at `app/ui/canvas_view.py:6175`
- 추가 신호
  - `CanvasView`는 이미 `SelectionController`, `SceneItemController`, `SceneOpsController`, `InsertController`를 보유한다.
  - 그럼에도 여러 구간에서 controller 내부 메서드를 다시 pass-through 하며 외부 표면을 계속 넓히고 있다.

권장 방향:

- `CanvasView`는 Qt 이벤트/scene/viewport 연결에 집중한다.
- 원자 라벨/병합/undo 조합은 `AtomLabelService` 같은 별도 모듈로 분리한다.
- 3D rotation 시작/업데이트/종료 상태는 `RotationSession` 또는 `RotationController`로 분리한다.
- 구조 삽입과 history 생성은 `StructureInsertService`로 뺀다.

첫 분리 대상으로는 `add_or_update_atom_label()` + `_merge_overlapping_atoms()` 묶음을 추천한다. 기능 경계가 비교적 명확하고, 현재 undo/merge/graphics 재구성까지 한 메서드 안에 섞여 있어 테스트 ROI가 가장 높다.

### 3.2 `core/tools.py`를 공통 입력 프레임워크로 재정리하기

`app/core/tools.py`는 이미 툴별 클래스로 나뉘어 있지만, 실제로는 press/move/release lifecycle, preview 생성/삭제, snap 계산, selection drag 처리 패턴이 반복된다.

- 대표 hotspot
  - `BondTool.on_mouse_press()` at `app/core/tools.py:402`
  - `TextTool.on_mouse_press()` at `app/core/tools.py:519`
  - `DeleteTool._erase_at_event()` at `app/core/tools.py:861`
  - `PerspectiveTool.on_mouse_press()` at `app/core/tools.py:1126`

권장 방향:

- preview가 있는 툴은 `PreviewToolBase`로 공통화한다.
- drag selection이 필요한 툴은 `_SelectionDragMixin`을 더 명시적인 인터페이스로 올린다.
- snap 계산, bond/atom hit fallback, scene item 삭제 규칙은 순수 함수로 추출한다.

현재 `test_tools_unit.py`가 존재하므로, 이 파일을 확장하면서 구조를 단계적으로 바꾸기 좋다.

### 3.3 `SceneOpsController`를 use-case 기준으로 분해하기

`SceneOpsController`는 이름과 달리 사실상 세 개의 하위 시스템을 동시에 담당한다.

- 삭제: `delete_selected_items()` at `app/ui/scene_ops_controller.py:30`
- 변환: `flip_selected_items()` at `app/ui/scene_ops_controller.py:330`
- 클립보드: `_selection_payload_for_clipboard()` / `paste_selection_from_clipboard()` at `app/ui/scene_ops_controller.py:454`, `:653`

문제는 selection 분류, model mutation, scene mutation, history command 생성, clipboard MIME 처리까지 한 메서드 흐름에서 같이 움직인다는 점이다. 이 구조는 작은 변경에도 회귀 범위를 넓힌다.

권장 방향:

- `SelectionDeleteService`
- `SelectionTransformService`
- `ClipboardSelectionService`

로 분리하고, controller는 캔버스에서 필요한 collaborator만 주입하는 얇은 조정자 역할만 남긴다.

### 3.4 `InsertController`는 현재 방향이 맞으므로 "마지막 20%"를 마무리하기

좋은 신호도 있다. `template_insert_logic.py`, `smiles_insert_logic.py`, `template_preview_logic.py`처럼 순수 계획 로직이 이미 분리되어 있다. 문제는 실제 commit 단계에서 history/scene mutation 조합이 다시 controller 안으로 회수된다는 점이다.

- 대표 함수
  - `load_smiles()` at `app/ui/insert_controller.py:84`
  - `_commit_smiles_insert()` at `app/ui/insert_controller.py:212`
  - `_commit_template_insert()` at `app/ui/insert_controller.py:385`

권장 방향:

- `load_smiles()`의 scene snapshot 수집과 `CompositeCommand` 구축을 별도 transaction builder로 분리
- template/smiles commit 결과를 "적용 계획" 객체로 만들어 controller는 적용만 수행

이 모듈은 완전 재설계보다 기존 순수 로직 추출 패턴을 그대로 확장하는 편이 맞다.

### 3.5 `MainWindow`는 데이터 기반 구성으로 바꾸기

`MainWindow`는 현재 동작 자체보다 유지보수 비용이 문제다.

- `_init_toolbars()` at `app/ui/main_window.py:478`
- `_apply_theme()` at `app/ui/main_window.py:1524`

리스크:

- `QAction`/`QToolButton` 생성이 수백 줄 inline wiring으로 이어진다.
- lambda 기반 연결이 많아 세부 동작 테스트가 어렵다.
- stylesheet 전체가 코드에 하드코딩되어 있어 변경 diff가 커지고 재사용이 어렵다.

권장 방향:

- 툴바/메뉴를 descriptor list로 선언
- 아이콘 생성과 action wiring을 builder 함수로 분리
- theme stylesheet는 별도 상수 모듈 또는 `.qss` 파일로 분리

이 작업은 기능 리스크보다 생산성 개선 성격이 강하므로 interaction 계층 정리 이후에 진행하는 것이 적절하다.

### 3.6 `RDKitAdapter` / `RDKitConversionHelper` 경계 정리

`RDKitAdapter`는 helper를 감싼 wrapper가 많은데, 현재 커버리지 누락도 대부분 이 표면에서 발생한다. 즉, "public API처럼 보이지만 실제 호출 경로는 제한적인" 메서드가 적지 않다.

권장 방향:

- 외부에서 실제로 사용하는 API만 남기고 나머지는 helper 내부로 숨기기
- 반대로 public API로 유지할 메서드라면 테스트를 추가해 계약을 명확히 하기

이 부분은 복잡도 감소 목적의 정리 작업으로 보는 편이 맞고, 기능 확장보다 API 표면 축소가 우선이다.

## 4. 테스트 커버리지 확장 권장안

현재 테스트는 많지만, 커버리지가 높은 영역과 낮은 영역이 분리되어 있다. 순수 로직 테스트와 GUI smoke test는 충분한데, controller 수준의 중간 계층 테스트가 부족하다.

### 4.1 가장 먼저 늘릴 테스트

#### `SceneOpsController`

현재 별도 전용 테스트 파일이 없다. 아래 케이스를 fake canvas 기반 단위 테스트로 추가하는 것이 가장 효율적이다.

- mixed selection 삭제 시 atom/bond/ring/mark/arrow/ts_bracket/orbital 분류가 올바른지
- atom 삭제 시 atom에 종속된 mark는 중복 제거되는지
- bond 하나만 선택된 fast path가 유지되는지
- flip 시 mark `dx/dy`, orbital `rotation`, note position이 올바르게 변환되는지
- clipboard payload version/type mismatch를 안전하게 거부하는지
- paste 시 atom id remap, selection 복원, paste offset 증가가 의도대로 동작하는지

#### `InsertController`

이 모듈도 전용 테스트가 사실상 없다.

- `load_smiles("")` no-op
- RDKit 변환 실패 시 경고 후 scene/state가 그대로 유지되는지
- preview center가 `None`일 때 commit이 취소되는지
- template insert에서 bond attach / free insert / benzene special case가 분리되는지
- template commit 중 bond merge seed가 중복 원자 생성을 막는지

#### `SceneItemController`

registry 관리 성격이 강해서 회귀가 숨어들기 쉽다.

- `restore_scene_item()`이 mark/note/ring/orbital/arrow registry를 올바르게 갱신하는지
- `remove_scene_item()`이 `selected_notes`, `_marks_by_atom`, handle target cleanup을 정확히 정리하는지
- ring 복원/삭제 시 관련 bond geometry refresh가 호출되는지

### 4.2 그 다음으로 늘릴 테스트

#### `CanvasView`

단순 utility 테스트는 이미 있으나, 고위험 상태 전이 테스트는 부족하다.

- 3D rotation
  - rotatable axis 선택
  - rigid fallback
  - selection에 mark만 포함된 경우
- atom merge / label
  - overlapping atom merge
  - duplicate bond 정리 우선순위
  - carbon dot <-> explicit label 전환
  - label change undo 기록
- structure insert
  - 제목 note 생성
  - 삽입 후 selection 복원

#### `core/tools.py`

현재 `test_tools_unit.py`는 존재하지만 일부 툴만 두껍게 테스트한다.

- `DeleteTool` drag erase 누적 command
- `PerspectiveTool` axis lock / selection-hit 분기
- `TextTool` bond 근처 클릭 시 atom 선택 fallback
- `ArrowTool` / `TSBracketTool` preview cleanup on deactivate

#### `MainWindow`

현재 테스트는 workbook/tab/icon/smoke 위주다.

- action descriptor 기반으로 바꾸면 toolbar wiring을 GUI smoke 대신 좁은 테스트로 검증 가능
- arrow settings dialog와 bond length dialog의 값 동기화/유효성 검사 테스트 추가 권장

### 4.3 선택적으로 보강할 테스트

#### `RDKitConversionHelper`

커버리지는 나쁘지 않지만 분기 실패 시 사용자 영향이 크다.

- alias attachment count 오류
- alias topology 오류
- unsupported label 메시지 formatting
- wedge/hash + non-single bond 오류
- multi-component scene layout 순서와 gap
- charge/radical annotation이 implicit hydrogen 판단에 미치는 영향

## 5. 유지하는 편이 좋은 영역

아래 영역은 지금 당장 구조를 흔들 이유가 크지 않다.

- `app/core/history.py`
- `app/core/template_geometry.py`
- `app/core/document_io.py`
- `app/ui/template_insert_logic.py`
- `app/ui/smiles_insert_logic.py`
- `app/ui/selection_hit_logic.py`

공통점은 책임 경계가 비교적 선명하고, 테스트도 이미 잘 깔려 있다는 점이다.

## 6. 권장 실행 순서

1. `SceneOpsController`, `InsertController`, `SceneItemController` 전용 단위 테스트를 먼저 추가한다.
2. `CanvasView`에서 label/merge와 structure insert를 별도 service로 분리한다.
3. `core/tools.py`에서 반복되는 입력 lifecycle/preview 처리 공통화를 진행한다.
4. `CanvasView`의 3D rotation 상태를 별도 controller/session으로 분리한다.
5. `MainWindow`를 데이터 기반 toolbar/theme 구조로 정리한다.
6. 마지막으로 `RDKitAdapter`의 wrapper 표면을 줄이거나 테스트 계약을 명확히 한다.

## 7. 결론

이 프로젝트는 "순수 로직 분리 -> 높은 테스트 효율"이라는 좋은 방향을 이미 일부 모듈에서 증명했다. 앞으로의 핵심은 새 기능 추가보다, 낮은 커버리지의 대형 orchestration 계층을 같은 방식으로 잘게 쪼개는 것이다.

총평:

- 지금 바로 손대야 할 곳: `CanvasView`, `SceneOpsController`, `InsertController`, `core/tools.py`
- 유지보수성 개선 효과가 큰 곳: `MainWindow`
- API 정리 성격이 강한 곳: `RDKitAdapter`
