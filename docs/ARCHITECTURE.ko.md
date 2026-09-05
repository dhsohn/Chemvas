# 아키텍처

## 현재 구현 지도 (규범 아님)

이 절은 마이그레이션 중인 현재 코드를 설명한다. 목표 패키지 경계와
의존 방향은 [ADR 0001](adr/0001-feature-oriented-modularization.md)에 정의되어
있다. 신규 기능은 아래의 평면 `core` / `ui` 배치를 복제하지 않고 ADR을
따른다.
- CanvasView (`app/chemvas/ui/canvas_view.py`): 입력 처리, 도구(tool) 디스패치, 선택 상태 관리, 그리고 모델/렌더/히스토리 업데이트의 조율을 담당한다. 저수준 드로잉 프리미티브(low-level drawing primitives)를 직접 소유해서는 안 된다.
- MoleculeModel (`app/chemvas/domain/document/model.py`): 순수한 원자/결합 데이터와 ID. Qt 의존성이 없다.
- RDKitAdapter (`app/chemvas/core/rdkit_adapter.py`): SMILES 가져오기, 물성 계산, 3D 좌표 생성, 별칭(alias) 확장, 미리보기 씬(preview scene) 구성을 담당하는 선택적 화학 백엔드. Alias 검증은 scene, XYZ, MOL, calculation-artifact 경로가 중앙에서 공유한다. Carbon-bound `PPh3`는 정확히 하나의 single bond를 가진 phosphonium `C-[P+](Ph)3`로만 확장하며, 모호한 attachment 또는 명시적인 전자 annotation은 fail closed한다. UI 코드는 RDKit을 필수 시작 의존성이 아니라 최선 노력(best-effort) 서비스로 취급해야 한다.
- Renderer (`app/chemvas/adapters/qt/renderer.py`): 순수
  `chemvas.features.rendering.acs1996_style` 정책을 사용하는 Qt 펜/브러시와
  폰트 설정.
- HistoryCommand (`app/chemvas/core/history.py`): 델타 기반 실행 취소/다시 실행(undo/redo). 다중 엔티티(multi-entity) 연산은 `CompositeCommand`로 그룹화되며, 이는 다시 실행 시 자식 델타 커맨드를 순서대로 적용하고 실행 취소 시 역순으로 적용한다.
- BondRenderer (`app/chemvas/ui/bond_renderer.py`): 결합 QGraphicsItem 생성/업데이트 및 기하 헬퍼(geometry helpers)로, CanvasView 컨텍스트에 의해 구동된다.
- Graphics items (`app/chemvas/ui/graphics_items.py`): 선택 불가능한 QGraphicsItem 래퍼(wrapper).
- Label layout (`app/chemvas/features/annotations`): 원자 레이블을 조판 런과 배치로 파싱하는 순수(Qt-free) 공개 API이며 화면과 아웃라인 내보내기 타이포그래피의 단일 소유자다.
- Figure export (`app/chemvas/features/export`): feature 패키지가 공개 API, Qt-free 대화상자/계획 규칙, 씬 범위 처리, SVG/PDF/raster 렌더러를 소유한다. 외부 호출자는 `chemvas.features.export`만 import하고 렌더러 모듈은 비공개 구현 세부사항으로 남는다. 순수 plan은 패딩이 적용된 소스 사각형과 물리 출력 크기를 포인트 단위로 계산한다. Qt 서비스는 보이는 콘텐츠를 수집하고, 일시적 오버레이를 제외하며, 가능한 경우 항목별 export bounds를 사용하고, 레이블을 아웃라인 처리한 뒤 SVG/PDF/PNG/TIFF로 렌더링한다. `unit_scale` 또는 `target_width_pt`로 줌과 무관한 크기를 결정하고 `scope`와 `background`로 내용과 배경을 선택한다.
- Template preview (`app/chemvas/features/insertion`, `app/chemvas/ui/insert_template_service.py`): insertion 공개 API가 벤젠의 방향족 내부선을 포함한 preview planning과 geometry를 소유한다. `InsertTemplateService`와 공용 `preview_scene_*` 모듈이 유일한 runtime/rendering 경로이며, 기존 벤젠 전용 preview service와 state는 삭제되었다.
- Bond preview (`app/chemvas/features/rendering/bond_preview.py`, `app/chemvas/ui/bond_preview_renderer.py`): feature policy는 Qt 값 없이 plain-double preview segment를 계산하고, 단일 Qt renderer가 concrete `BondRenderer`를 통해 preview item을 생성·갱신·부착·정리한다. Canvas access leaf는 두 활성 호출자를 지원하며 resolver dataclass, 호출별 lambda 배선, 별도 geometry/scene-item 역할 모듈은 삭제되었다.
- Hover (`app/chemvas/features/hover`, `app/chemvas/ui/hover.py`): feature 공개 API가 Qt-free transient state와 갱신 정책을 소유한다. 캔버스당 하나의 `HoverController`가 Qt 조율을 맡고, `hover_rendering.py`가 graphics item helper를 소유한다. `canvas_hover_state.py`는 eager import graph를 비순환으로 유지하기 위한 단일 함수 runtime-state leaf로 남는다. `CanvasRuntimeServices.hover`는 controller를 직접 노출하며, 기존 hover access/ports/bundle과 4개 service 스택은 삭제되었다.
- Domain document (`app/chemvas/domain/document`): Qt-free 분자 모델과 버전이 있는 문서/클립보드 직렬화·검증 정책을 소유한다. 기존 `chemvas.core.model`과 `document_state` 경로는 삭제되었다.
- 계산 plan과 artifact(`app/chemvas/domain/document/calculation_plan.py`, `app/chemvas/domain/document/precomplex_profile.py`, `app/chemvas/features/calculation_bundle`, `app/chemvas/bootstrap/calculation_bundle.py`): document domain은 endpoint precomplex 상태를 포함한 엄격한 Plan v2 스키마를 소유한다. Domain profile registry는 현재 placement profile의 sample bound, radius table, table hash, 과학 provenance의 단일 immutable owner다. Qt 비의존 feature API는 연결 성분 선택·전하 의미 검증·endpoint별 역할·correspondence readiness·결합 변화·결정론적 path precheck·제한된 rigid-placement 후보 생성을 소유한다. Calculation dialog는 included 원자를 ID 기반 대응표 하나로 투영하고 부분 draft와 명시적인 unmapped 선택을 보존한 뒤, 최종 후보를 같은 feature/domain 검증 경로에 맡긴다. `calculation_mapping_highlight.py`는 dialog 수명에 한정된 비선택 atom-ID label을 mapping 상태에 따라 색칠하며 document serialization, selection state, history에 넣지 않고 모든 dialog 종료에서 제거한다. bootstrap은 `.chemvas` I/O, 선택적 RDKit 조립, 결정적 단일파일 step 직렬화, 현재 profile의 후보 생성·검사·선택·결정론적 재생성, reactant identity 순서의 path endpoint 생성, 비덮어쓰기 원자적 공개를 맡는다. `application.main`은 Qt import 전에 `inspect`, `attach-plan`, `inspect-plan`, `generate-precomplex`, `inspect-precomplex`, `select-precomplex`, `pack-step`을 dispatch한다.
- Agent 문서 patch(`app/chemvas/features/document_patch`, `app/chemvas/bootstrap/document_patch.py`): Qt/provider 비의존 feature API가 결정적 전체 graph 검사, 엄격한 Graph Patch v1 검증, 복사본 기반 순차 mutation, 의존 좌표 이동, 최종 문서/Calculation Plan gate를 소유한다. bootstrap은 원본 bytes를 한 번 읽어 hash하고, 중복 key·비표준 JSON을 거부하며, 후보를 결정적으로 encode한 뒤 공용 원자적 비덮어쓰기 파일 생성기로 공개한다. `inspect-document`와 `apply-patch`는 Qt 전에 dispatch되며 Chemvas 내부에서 자연어 모델이나 화학 추론을 실행하지 않는다.
- 창 없는 문서 렌더링(`app/chemvas/bootstrap/document_render.py`): bootstrap은 파일과 출력 자원 계약을 먼저 검증한 뒤 보이지 않는 `QApplication`과 `CanvasView`를 지연 조립한다. 적용된 문서는 `CanvasDocumentSessionService.plan_figure_export`로 painting 전 자원 preflight를 거치고 GUI와 같은 전체 sheet figure-export 경로로 private 임시 저장소에 SVG/PNG를 렌더한다. 제한을 통과한 출력만 기존 경로를 덮어쓰지 않고 원자적으로 공개하며 원본/출력 hash, point/pixel 크기, 문서 버전이 render report v1을 이룬다. 데스크톱 창, session recovery, RDKit loading, editable SVG payload, PDF, TIFF는 이 명령의 범위 밖이다.
- 이전된 feature 정책 (`app/chemvas/features/{export,session,annotations,rendering,insertion,selection,hover}`): 각 패키지는 응집된 planning/geometry/state 계약을 하나의 공개 API로 제공한다. 기존 평면 호환 모듈은 삭제되었고 `test_package_dependencies.py`가 재도입을 막는다.
- 메인 창 조립: `chemvas.shell.main_window`가 얇은 Qt 셸을 소유하고, `chemvas.bootstrap`이 runtime/service 조립·창 등록·문서 열기·앱 시작을 소유한다. Qt 파일 열기 이벤트는 `chemvas.adapters.qt`를 통해 들어온다.

## 전환기 UI 규율 (ports / access / state / services)
`app/chemvas/ui` 패키지는 구조 전환 중 실제 책임을 분리하는 경우에만 작은 역할 모듈을 유지한다. 목표는 `CanvasView`와 `MainWindow`를 얇은 Qt 셸로 유지하고(갓 오브젝트 금지), 모든 서비스를 헤드리스로 생성 가능하게 하며, 모든 의존성을 명시적으로 만드는 것이다.

이 규칙들은 평면 패키지에 남아 있는 코드의 마이그레이션 제약으로
유지한다. 모든 신규 기능이 복제할 템플릿은 아니며, 신규 feature 패키지는
실제 경계가 필요할 때만 역할별 모듈을 만든다.

- **State 모듈** (`*_state.py`): 아직 이전되지 않은 관심사는 dataclass 하나와 `<name>_state_for(canvas)` 접근자를 사용한다. 이 접근자들은 eager 생성되는 `CanvasRuntimeState` 컨테이너(`chemvas.ui.canvas_runtime_state.py`)에서 자기 필드를 직접 읽는다 — `return cast(CanvasGraphState, canvas.runtime_state.graph_state)`. 이 컨테이너는 `slots=True` dataclass여서 이름이 바뀌거나 틀린 필드는 상태를 조용히 둘로 쪼개는 대신 즉시 실패한다. lazy 부착도 plain-attribute fallback도 하지 않는다: 캔버스에 상태를 만들어 붙이던 `ensure_canvas_state`와 `canvas_state_object` seam은 모두 제거됐고, `document_metadata_state_for`도 다른 모든 상태 접근자와 같은 runtime-container 직접 조회 규칙을 따른다. `SheetSetupState`가 sheet 크기·방향·rect의 유일한 소유자이며 이 값들을 캔버스에 별도로 미러링하지 않는다. transaction snapshot도 선택적 runtime field를 컨테이너에서만 조회한다. 컨테이너가 없는 가벼운 model/scene-only capture는 같은 이름의 canvas attribute로 fallback하지 않고 runtime state를 생략한다. focused 테스트는 `tests/runtime_state.canvas_runtime_state(**states)`로 부분 컨테이너를 만들며, 이 헬퍼가 필드명을 실제 컨테이너와 대조한다. `model`은 runtime 필드가 아니라 캔버스 직접 속성이지만 setup이 생성하므로 `model_for`는 그것을 읽기만 한다 — 없는 캔버스는 배선 버그이며 빈 문서를 새로 만들어 덮지 않는다. `renderer`, `rdkit`, `bond_renderer`는 setup이 생성하는 직접 collaborator이며 각 access 모듈이 lazy 생성이나 fallback 없이 조회한다. 이전된 hover 상태는 `chemvas.features.hover`가 소유하며, 얇은 UI leaf는 필수 runtime field를 직접 읽을 뿐 부착하거나 fallback하지 않는다. input-view는 실제 상태 dataclass를 `input_view_state.py`에, 조회를 canonical `input_view_access.py`에 두고 callback state는 dataclass와 getter를 한 모듈에 유지한다. `test_state_accessors_read_the_runtime_container_directly`는 범위 안의 접근자를 **열거**하며, 컨테이너를 더 이상 읽지 않는 접근자를 위반으로 잡는다 — 이름만 바꾼 조회 헬퍼도, 자기 상태를 만들어내는 접근자도 통과하지 못한다.
- **Access 모듈** (`*_access.py`): 연산 하나를 감싸는 자유 함수(`foo_for(canvas)`). `canvas.services`에 직접 접근할 수 없고, 서비스 조회는 대응하는 ports 모듈에 위임한다.
- **Ports 모듈** (`*_ports.py`): 서비스 컨테이너(`canvas_services_for` / window 비공개 저장소)를 해석할 수 있는 유일한 모듈. 그 외 모든 코드는 협력자를 주입받거나 port를 호출한다. 생산 코드의 port는 canonical `CanvasRuntimeServices` API만 사용한다. 응집된 그룹은 묶어서 유지하고 `graph_service`, `tool_controller`, `hover`, `atom_label_service` 같은 단일 runtime은 직접 보관한다. 평면 서비스 별칭과 duck-typed 생산 adapter는 삭제되었고, 집중 테스트는 `tests/runtime_services.py`로 부분 canonical runtime을 만든다.
- **서비스와 컨트롤러**: `chemvas.ui.canvas_services.py`에서 캔버스당 한 번, 명시적 키워드 주입으로 조립된다 — 서비스 내부의 서비스 로케이터 금지, 누락된 배선을 숨기는 `=None` 협력자 기본값 금지. 조립은 응집된 그룹은 `CanvasRuntimeServices`의 bundle로 보관하고, runtime이 하나면 단일 멤버 bundle을 만들지 않고 직접 보관한다. 기존 graph/tool wrapper bundle과 builder 주입 composer 계층은 삭제되었다.
- **core는 UI 및 Qt와 분리된다**: `app/chemvas/core`는 모듈 수준에서 `ui`를 import하지 않는다(`chemvas.core.history.py`의 지연 해석 프로토콜 구현만 예외). 또한 Qt를 import하지 않으며, 구체 Qt 렌더링은 `chemvas.adapters.qt.renderer`에 둔다. 새로운 core-to-Qt 의존성은 금지한다.
- **RDKit은 선택적이다**: 앱 시작 경로에서 절대 하드 import가 되어서는 안 된다. RDKit이 필요한 기능은 그것이 없을 때 우아하게 축소되거나 명확한 메시지와 함께 실패한다 — `chemvas.core.rdkit_adapter` 참조. 아래 3D 제약은 이 규칙이 export 동작에 대해 무엇을 뜻하는지를 적은 것이고, 규칙 자체는 일반적이다.

이 규칙들은 `tests/test_architecture_boundaries.py`가 강제한다. 신규 규칙은
의존성 계약이나 일반 패턴 금지로 작성한다. 일부 전환기 검사는 아직 제거된
이름이나 구현 위치를 고정하고 있으므로, 각 feature 이전 시 패키지/공개 API
계약으로 교체한 뒤 퇴역시킨다.

이 규율의 알려진 트레이드오프(의도적으로 수용): 실재하는 간접 비용(ui LOC의 약 20%가 배선)과 캔버스 seam의 약한 정적 타이핑(`canvas: Any`). 하나의 불변식이 여러 작은 모듈에 걸칠 때는 일관성 계약을 소유 모듈 한 곳에 문서화해야 한다 — 파생 그래프 인덱스의 예로 `chemvas.features.graph` 패키지 독스트링과 `CanvasGraphService.bond_id_between_with_repair` 패턴을 참고.

## Feature Qt 마이그레이션 목록

목표 경계는 구체 Qt 통합을 `chemvas.adapters`에 둔다. 다만 진행 중인 namespace
마이그레이션에는 아직 고정된 일부 feature 구현 모듈의 직접 Qt import가 남아 있다.
`tests/test_package_dependencies.py`의 `FEATURE_QT_MIGRATION_ALLOWLIST`가 실행 가능한
목록이다. 새 모듈은 추가할 수 없고, 각 adapter 이전에서 해당 항목을 제거한다.

다만 **목록을 비우는 것은 현재 도달 가능한 목표가 아니다** — 남은 12항목 중 8건은 환원
불가능한 Qt이고(figure export는 입력 자체가 `QGraphicsScene`이다), 나머지를 옮기는 것은
실제 의존을 없애지 못한 채 port와 배선만 늘린다. 측정 근거는
[ADR 0001](adr/0001-feature-oriented-modularization.md)에 있다. 종료 형태가 결정되기
전까지 이 목록은 **줄어들기만 하는 동결 목록**으로 다룬다.

## 트랜잭션과 복구 소유권

- `CanvasHistoryService`는 undo/redo stack 정책과 불변 `HistoryStackSnapshot` 값의 유일한 소유자다. 최상위 exact undo/redo 연산은 문서 savepoint를 하나만 캡처하고, 중첩 command는 그 연산에 위임한다.
- `chemvas.ui.transactions.document.DocumentSavepoint`는 문서 전체 capture, restore, verify, release의 공개 소유자다. 같은 패키지의 하위 object-graph, scene-runtime, scene-rect primitive를 조합한다. `history_commands`는 command class만 소유하며 private snapshot toolkit을 내보내지 않는다.
- `chemvas.domain.transactions`는 프레임워크와 무관한 `RestoreOutcome` 검증, 복구 오류 note 부착, 1회 restore helper만 소유한다.
- restore는 한 번 적용하고 한 번 검증한다. exact 복원을 입증하지 못하면 history는 ADR 0002의 보수적인 fail-closed stack 정책을 적용하고 durable recovery는 autosave/session restore에 맡긴다. 제거된 retry, authority channel, compatibility probing, 병렬 stack snapshot 계층은 다시 도입할 수 없다.
- Autosave session 소유권은 PID와 process-creation identity의 조합에 묶인다. `session.json`은 동시에 실행 중인 이전 바이너리도 읽을 수 있는 엄격한 version-1 형태를 유지하고, 원자적으로 기록되는 `owner.json` sidecar가 새 reader를 위해 PID와 생성 identity를 연결한다. 같은 identity의 live PID 또는 identity를 읽을 수 없는 live PID는 그대로 보존하며, 다른 identity일 때만 PID 재사용이 입증되어 crashed session을 복구할 수 있다. identity가 없는 legacy manifest는 보수적인 live-PID 정책을 유지한다.
- Desktop document path는 canonical `.chemvas`다. Startup, OS-open, File Open, Open Recent, clean-session restore는 `.json` drawing path를 거부하거나 무시한다. 비정상 session snapshot은 현재 내부 autosave state를 복구할 수 있지만, 지원하지 않는 원본 path는 지우므로 recovered canvas는 path에 연결되지 않은 미저장 문서다.

## 데이터/렌더 흐름 (Data/Render Flow)
Tools -> CanvasView -> MoleculeModel 변경(mutation) -> Renderer/BondRenderer -> QGraphicsScene 업데이트 -> HistoryCommand 푸시.

3D 흐름: 내보내기 커맨드 또는 미리보기 새로고침 -> 현재 분자 / 활성 원자-결합 선택 -> MoleculeModel 서브그래프 + 원자 마크 주석(atom mark annotations) -> RDKitAdapter 변환 그래프 구성 -> RDKit 3D 임베딩 -> `.xyz` 라이터(writer) 또는 미리보기 씬.

계산 흐름: headless `inspect` -> 검증된 `.chemvas` state -> 안정적으로 index된 연결 성분·결합·alias attachment 목록; `attach-plan` 또는 Calculation dialog -> 재사용 state, endpoint별 역할, 명시적 included-atom 대응표, Calculation Plan v2를 가진 v7 문서; dialog 수명 동안 mapping 상태 색상의 임시 atom-ID label; `inspect-plan` -> mapping/readiness와 path precheck 보고. 단일 성분 쌍은 바로 `pack-step`으로 갈 수 있다. 양 endpoint가 두 성분이면 `generate-precomplex`가 명시된 contact와 environment를 요구한다. Request v2는 `chemvas-rigid-precomplex-placement/2`를 명시해야 하며 다른 request version/profile은 모두 거부한다. 명령은 제한된 결정론적 rigid-placement ensemble을 Calculation Plan v2에 기록하고, `inspect-precomplex`가 정확한 XYZ·profile·radius provenance·metric을 노출하며, `select-precomplex`가 검토한 한 쌍을 기록한다. `inspect-plan`, selection, Graph Patch, `pack-step`은 reviewed-pair identity·profile·basis validator를 공유하므로 stale하거나 atomic하지 않은 쌍을 ready로 보고하지 않는다. 두 endpoint는 source-document와 environment provenance를 공유해야 하며, basis는 원소·좌표·결합 의미(방향성 wedge/hash 포함), environment, 유효 charge/radical mark를 묶되 표시 전용 color와 label visibility는 제외한다. `pack-step`은 현재 persisted profile로 각 endpoint 후보를 재생성하고 전하·다중도·완전 bijection gate를 적용한 뒤 검토한 placement profile과 radius provenance까지 담은 `factory/machine-observation` v1 / `chemistry/elementary-step` v1 `machine.json` 하나를 원자적으로 공개한다. 적합한 artifact는 reactant identity 순서의 endpoint XYZ와 공통 0-based 반응중심 index를 담는다. GUI는 정확히 공유된 ID와 선택적인 same-element 구조 mapping을 제안할 뿐 반응기구를 추론하지 않는다. Chemvas는 contact를 만들거나 후보를 자동 선택하거나 최적화·안정성을 주장하지 않으며, 후속 양자화학 최적화와 과학적 검토를 대체하지 않는다.

Agent 편집 흐름: `inspect-document` -> 정확한 source SHA-256과 안정적인 atom/bond 목록 -> 신뢰하지 않는 Graph Patch v1 -> 엄격한 schema/hash gate -> deep copy에서 순차 mutation -> 구조 및 Calculation Plan 의미 검증 -> 결정적 후보 hash -> dry-run 보고 또는 단 한 번의 원자적 비덮어쓰기 `.chemvas` 공개. 입력 파일 버전과 범위 밖 scene state를 보존하며, 어느 operation이나 stale plan이라도 실패하면 output은 없다.

창 없는 렌더 흐름: `render-document` -> 원본 1회 읽기/hash 및 record-count gate -> 검증된 state를 invisible canvas에 적용 -> canonical whole-sheet export plan -> point/pixel 자원 gate -> private SVG/PNG 렌더 -> output byte gate -> 단 한 번의 원자적 비덮어쓰기 공개 -> hash·크기 JSON report. painting에는 지연 import한 Qt가 필요하지만 RDKit과 desktop session-recovery service는 시작하지 않는다.

## 복합 그룹화 (Composite Grouping)
하나의 연산이 여러 엔티티 유형을 동시에 다룰 때(예: 원자 생성과 결합 생성), CanvasView는 개별 델타 커맨드를 단일 `CompositeCommand`로 그룹화하여 전체 연산이 원자적으로(atomically) 실행 취소/다시 실행되도록 한다.

## 3D 변환 제약 (3D Conversion Constraints)
- 내보내기 범위는 화학 그래프 데이터로 제한된다. 화살표, 대괄호 주석(bracket annotations), 자유 텍스트, 기타 씬 전용 주석은 내보내기 페이로드를 구성할 때 무시해야 한다.
- RDKit은 선택적으로 유지된다. 사용 불가능한 경우, 내보내기 동작은 앱 시작에 하드 의존성을 도입하기보다는 명확한 메시지와 함께 실패해야 한다.
- 캔버스의 전하/라디칼 마크(charge/radical marks)는 변환 전에 원자별 주석으로 정규화되어야 하며, 그래야 형식 전하(formal charge)와 라디칼 전자가 RDKit으로 보존된다.
- 별칭의 정본은 `chemvas.domain.atom_aliases.ATOM_ALIAS_DEFINITIONS`이며 현재 `Me`, `Et`, `OH`, `Ph`, `PPh3`, `OMe`, `Boc`, `CO2Me`, `t-Bu`, `tBu`, `i-Pr`, `CF3`, `OTs`, `Ts`, `OMs`, `Ms`, `OTf`, `Tf`, `Ns`, `OAc`, `Ac`를 포함한다. 이 별칭들은 변환 시점에 명시적 프래그먼트로 확장되어야 한다. 지원되지 않는 약어는 추측하지 말고 확실하게(loudly) 실패해야 한다.
- 쐐기/해시 결합(Wedge/hash bonds)은 단일 결합에 대해서만 RDKit 결합 방향으로 변환되어야 한다. 잘못된 입체(stereo) 사용은 정확한 메시지와 함께 실패해야 한다.
- SMILES 삽입은 RDKit wedging 후 결합 끝점을 복사해 절대 사면체 입체배치를 보존한다. 지정된 이중결합·비사면체·상대/라세미 입체화학은 거부한다. Molecule Info 식별자는 미리보기 변환을 재사용하되, 원소 라벨만 허용하는 기존 정책을 유지한다.
- `.xyz`는 좌표 전용이다. 결합 차수(bond order)와 반응 의미(reaction semantics)는 출력 포맷에 보존되지 않으며 왕복 가능한(round-trippable) 상태로 취급해서는 안 된다.
- Calculation Plan v2는 명시적 state, `included`/`context_only` membership, endpoint별 역할, source atom correspondence, step-side precomplex ensemble, reviewer 선택을 저장한다. 유일한 placement profile `chemvas-rigid-precomplex-placement/2`는 모든 지원 원소에 Cordero(2008) Table 2 covalent radius(C-sp3, Fe-low-spin, Co-low-spin selector)와 Alvarez(2013) Table 1 van der Waals radius를 사용하고 exact provenance를 저장·검증한다. Plan은 역할·contact·spin state·coordination·반응기구를 추론하지 않는다. elementary-step handoff는 공통 envelope와 inline domain payload 안에 provenance, mapping, bond change, 조건부 identity-ordered endpoint pair를 담은 `machine.json` 하나다. 검토된 rigid placement와 empirical-radius clash score도 heuristic 초기 추정값이며 후속 양자화학 최적화와 연구자 검토가 필요하다.
- 미리보기 창은 사용자가 보는 것과 실제로 내보내지는 것 사이의 불일치를 피하기 위해 `.xyz` 내보내기와 동일한 변환 경로를 재사용해야 한다.
- 3D 미리보기는 **View ▸ Molecule Info**에서 별도의 모덜리스(modeless) 창으로 열린다. 선택된 구조 변환 경로를 사용하고, 선택된 분자에 대한 `Export 3D XYZ` 동작을 소유하며, 선택된 화학 구조가 없을 때는 빈 미리보기를 표시한다.
- 열려 있는 각 캔버스 탭은 자체 파일 경로와 clean/dirty 다이제스트(digest)를 가진 독립적인 문서다. `.chemvas` 로딩은 표준 단일 캔버스 페이로드만 허용한다.
- `.chemvas` 문서는 version 7만 읽고 쓴다. Canonical payload는 deleted-slot tombstone이 없는 compact bond array를 사용하며 plan이 있으면 Calculation Plan v2다. Calculation plan은 bond 위치가 아니라 안정적 atom id와 완전한 연결 성분 atom-id 집합을 참조한다.

## 리팩토링 순서

현재 모듈화 순서, 완료 조건, 의존성 규칙은
[ADR 0001](adr/0001-feature-oriented-modularization.md)에서 관리한다.
transaction/history rollback의 소유권·위협 모델·fail-closed 복구 의미론은
[ADR 0002](adr/0002-single-rollback-kernel.md)에서 결정한다.
selection move savepoint의 범위와 수용한 제한은
[ADR 0003](adr/0003-scoped-move-savepoint.md)에서 결정한다.
