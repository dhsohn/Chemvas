# 아키텍처

## 현재 구현 지도 (규범 아님)

이 절은 마이그레이션 중인 현재 코드를 설명한다. 목표 패키지 경계와
의존 방향은 [ADR 0001](adr/0001-feature-oriented-modularization.md)에 정의되어
있다. 신규 기능은 아래의 평면 `core` / `ui` 배치를 복제하지 않고 ADR을
따른다.
- CanvasView (`app/chemvas/ui/canvas_view.py`): 입력 처리, 도구(tool) 디스패치, 선택 상태 관리, 그리고 모델/렌더/히스토리 업데이트의 조율을 담당한다. 저수준 드로잉 프리미티브(low-level drawing primitives)를 직접 소유해서는 안 된다.
- MoleculeModel (`app/chemvas/domain/document/model.py`): 순수한 원자/결합 데이터와 ID. Qt 의존성이 없다.
- RDKitAdapter (`app/chemvas/core/rdkit_adapter.py`): SMILES 가져오기, 물성 계산, 3D 좌표 생성, 별칭(alias) 확장, 미리보기 씬(preview scene) 구성을 담당하는 선택적 화학 백엔드. UI 코드는 이를 필수 시작 의존성이 아니라 최선 노력(best-effort) 서비스로 취급해야 한다.
- Renderer (`app/chemvas/core/renderer.py`): 스타일, 펜/브러시, 폰트 설정.
- HistoryCommand (`app/chemvas/core/history.py`): 델타 기반 실행 취소/다시 실행(undo/redo). 다중 엔티티(multi-entity) 연산은 `CompositeCommand`로 그룹화되며, 이는 다시 실행 시 자식 델타 커맨드를 순서대로 적용하고 실행 취소 시 역순으로 적용한다.
- BondRenderer (`app/chemvas/ui/bond_renderer.py`): 결합 QGraphicsItem 생성/업데이트 및 기하 헬퍼(geometry helpers)로, CanvasView 컨텍스트에 의해 구동된다.
- Graphics items (`app/chemvas/ui/graphics_items.py`): 선택 불가능한 QGraphicsItem 래퍼(wrapper).
- Label layout (`app/chemvas/features/annotations`): 원자 레이블을 조판 런과 배치로 파싱하는 순수(Qt-free) 공개 API이며 화면과 아웃라인 내보내기 타이포그래피의 단일 소유자다.
- Figure export (`app/chemvas/features/export`): feature 패키지가 공개 API, Qt-free 대화상자/계획 규칙, 씬 범위 처리, SVG/PDF/raster 렌더러를 소유한다. 외부 호출자는 `chemvas.features.export`만 import하고 렌더러 모듈은 비공개 구현 세부사항으로 남는다. 순수 plan은 패딩이 적용된 소스 사각형과 물리 출력 크기를 포인트 단위로 계산한다. Qt 서비스는 보이는 콘텐츠를 수집하고, 일시적 오버레이를 제외하며, 가능한 경우 항목별 export bounds를 사용하고, 레이블을 아웃라인 처리한 뒤 SVG/PDF/PNG/TIFF로 렌더링한다. `unit_scale` 또는 `target_width_pt`로 줌과 무관한 크기를 결정하고 `scope`와 `background`로 내용과 배경을 선택한다.
- Domain document (`app/chemvas/domain/document`): Qt-free 분자 모델과 버전이 있는 문서/클립보드 직렬화·검증 정책을 소유한다. 기존 `chemvas.core.model`과 `document_state` 경로는 삭제되었다.
- 이전된 feature 정책 (`app/chemvas/features/{export,session,annotations,rendering,insertion,selection}`): 각 패키지는 응집된 planning/geometry/state 계약을 하나의 공개 API로 제공한다. 기존 평면 호환 모듈은 삭제되었고 `test_package_dependencies.py`가 재도입을 막는다.
- 메인 창 조립: `chemvas.shell.main_window`가 얇은 Qt 셸을 소유하고, `chemvas.bootstrap`이 runtime/service 조립·창 등록·문서 열기·앱 시작을 소유한다. Qt 파일 열기 이벤트는 `chemvas.adapters.qt`를 통해 들어온다.

## 전환기 레거시 UI 규율 (ports / access / state / services)
`app/chemvas/ui` 패키지는 역할이 고정된 다수의 작은 모듈로 의도적으로 분리되어 있다. 목표는 `CanvasView`와 `MainWindow`를 얇은 Qt 셸로 유지하고(갓 오브젝트 금지), 모든 서비스를 헤드리스로 생성 가능하게 하며(전체 테스트 스위트가 `SimpleNamespace` 캔버스로 약 20초에 실행), 모든 의존성을 명시적으로 만드는 것이다.

이 규칙들은 평면 레거시 패키지에 남아 있는 코드의 마이그레이션 제약으로
유지한다. 모든 신규 기능이 복제할 템플릿은 아니며, 신규 feature 패키지는
실제 경계가 필요할 때만 역할별 모듈을 만든다.

- **State 모듈** (`*_state.py`): 관심사당 dataclass 하나와 `<name>_state_for(canvas)` 접근자. 모든 상태 접근자는 `ensure_canvas_state(canvas, name, factory)`(`chemvas.ui.canvas_state_lookup.py`)를 거치며, 조회와 부착에 하나의 이름만 사용한다. 실제 캔버스에서는 모든 상태가 eager 생성되는 `CanvasRuntimeState` 컨테이너(`chemvas.ui.canvas_runtime_state.py`)의 필드로 존재한다. 컨테이너는 strict하다 — 컨테이너에 없는 필드를 요청하는 접근자는 그림자 사본을 조용히 부착하는 대신 즉시 실패한다. 일부 상태(`model`, `renderer`, `bond_renderer`, `rdkit`)는 의도적으로 캔버스 직접 속성으로 저장되며 `runtime_field=False`를 사용한다. 새 상태 추가 시: dataclass + 접근자 + `CanvasRuntimeState` 필드가 세트이며, `test_state_accessor_names_match_runtime_state_container`가 동기화를 강제한다.
- **Access 모듈** (`*_access.py`): 연산 하나를 감싸는 자유 함수(`foo_for(canvas)`). `canvas.services`에 직접 접근할 수 없고, 서비스 조회는 대응하는 ports 모듈에 위임한다.
- **Ports 모듈** (`*_ports.py`): 서비스 컨테이너(`canvas_services_for` / window 비공개 저장소)를 해석할 수 있는 유일한 모듈. 그 외 모든 코드는 협력자를 주입받거나 port를 호출한다. 생산 코드의 port는 묶음형 `CanvasRuntimeServices` API(예: `services.auxiliary.atom_label_service`)만 사용한다. 기존 평면 서비스 이름은 경량 테스트 fixture를 위한 임시 호환 표면이며, 생산 소비자에서의 사용은 아키텍처 ratchet이 금지한다.
- **서비스와 컨트롤러**: `chemvas.ui.canvas_service_composer.py`에서 캔버스당 한 번, 명시적 키워드 주입으로 조립된다 — 서비스 내부의 서비스 로케이터 금지, 누락된 배선을 숨기는 `=None` 협력자 기본값 금지. composer는 기존 기능 bundle들을 `CanvasRuntimeServices`에 그대로 보관하여 수십 개 협력자를 평면화하지 않고 캔버스마다 안정적인 bundle identity 하나를 유지한다.
- **core는 UI와 분리되며, Qt 마이그레이션 부채는 하나만 허용한다**: `app/chemvas/core`는 모듈 수준에서 `ui`를 import하지 않는다(`chemvas.core.history.py`의 지연 해석 프로토콜 구현만 예외). `chemvas.core.renderer.py`는 현재 유일한 직접 Qt 의존성으로, 네임스페이스 이전 중 Qt 어댑터로 이동할 전환 부채다. 새로운 core-to-Qt 의존성은 금지한다.

이 규칙들은 `tests/test_architecture_boundaries.py`가 강제한다. 신규 규칙은
의존성 계약이나 일반 패턴 금지로 작성한다. 일부 레거시 검사는 아직 제거된
이름이나 구현 위치를 고정하고 있으므로, 각 feature 이전 시 패키지/공개 API
계약으로 교체한 뒤 퇴역시킨다.

이 규율의 알려진 트레이드오프(의도적으로 수용): 실재하는 간접 비용(ui LOC의 약 20%가 배선)과 캔버스 seam의 약한 정적 타이핑(`canvas: Any`). 하나의 불변식이 여러 작은 모듈에 걸칠 때는 일관성 계약을 소유 모듈 한 곳에 문서화해야 한다 — 파생 그래프 인덱스의 예로 `chemvas.ui.graph_index_operations.py`와 `CanvasGraphService.bond_id_between_with_repair` 패턴을 참고.

## 트랜잭션과 복구 소유권

- `chemvas.domain.transactions`는 프레임워크와 무관한 복구 결과, hostile descriptor에도 안전한 bound attribute port, 재시도/오류 보존, 정확한 history stack authority snapshot을 소유한다.
- `chemvas.ui.transactions`는 Qt-aware command payload, 객체 그래프, scene-item attach, scene-rect savepoint를 소유한다. 기존 평면 snapshot 모듈은 삭제되었고 아키텍처 ratchet이 재도입을 막는다.
- 트랜잭션 동작을 하나의 범용 context manager로 합치지 않는다. 되돌릴 수 있는 mutation은 절대 snapshot을 복원하고, 문서 교체는 이전 문서를 복원하거나 fail-closed하며, 장시간 drag는 savepoint형 authority를 사용하고, scene reset은 Qt item 파괴 후 빈 상태로 수렴한다. 의미가 같은 부분에만 공통 primitive를 사용한다.

## 데이터/렌더 흐름 (Data/Render Flow)
Tools -> CanvasView -> MoleculeModel 변경(mutation) -> Renderer/BondRenderer -> QGraphicsScene 업데이트 -> HistoryCommand 푸시.

3D 흐름: 내보내기 커맨드 또는 미리보기 새로고침 -> 현재 분자 / 활성 원자-결합 선택 -> MoleculeModel 서브그래프 + 원자 마크 주석(atom mark annotations) -> RDKitAdapter 변환 그래프 구성 -> RDKit 3D 임베딩 -> `.xyz` 라이터(writer) 또는 미리보기 씬.

## 복합 그룹화 (Composite Grouping)
하나의 연산이 여러 엔티티 유형을 동시에 다룰 때(예: 원자 생성과 결합 생성), CanvasView는 개별 델타 커맨드를 단일 `CompositeCommand`로 그룹화하여 전체 연산이 원자적으로(atomically) 실행 취소/다시 실행되도록 한다.

## 3D 변환 제약 (3D Conversion Constraints)
- 내보내기 범위는 화학 그래프 데이터로 제한된다. 화살표, 대괄호 주석(bracket annotations), 자유 텍스트, 기타 씬 전용 주석은 내보내기 페이로드를 구성할 때 무시해야 한다.
- RDKit은 선택적으로 유지된다. 사용 불가능한 경우, 내보내기 동작은 앱 시작에 하드 의존성을 도입하기보다는 명확한 메시지와 함께 실패해야 한다.
- 캔버스의 전하/라디칼 마크(charge/radical marks)는 변환 전에 원자별 주석으로 정규화되어야 하며, 그래야 형식 전하(formal charge)와 라디칼 전자가 RDKit으로 보존된다.
- 지원되는 별칭(`Me`, `Et`, `OH`, `Ph`, `OMe`, `Boc`, `CO2Me`, `t-Bu`, `i-Pr`)은 변환 시점에 명시적 프래그먼트로 확장되어야 한다. 지원되지 않는 약어는 추측하지 말고 확실하게(loudly) 실패해야 한다.
- 쐐기/해시 결합(Wedge/hash bonds)은 단일 결합에 대해서만 RDKit 결합 방향으로 변환되어야 한다. 잘못된 입체(stereo) 사용은 정확한 메시지와 함께 실패해야 한다.
- `.xyz`는 좌표 전용이다. 결합 차수(bond order)와 반응 의미(reaction semantics)는 출력 포맷에 보존되지 않으며 왕복 가능한(round-trippable) 상태로 취급해서는 안 된다.
- 미리보기 창은 사용자가 보는 것과 실제로 내보내지는 것 사이의 불일치를 피하기 위해 `.xyz` 내보내기와 동일한 변환 경로를 재사용해야 한다.
- 3D 미리보기는 툴바에서 별도의 모덜리스(modeless) 창으로 열린다. 선택된 구조 변환 경로를 사용하고, 선택된 분자에 대한 `Export 3D XYZ` 동작을 소유하며, 선택된 화학 구조가 없을 때는 빈 미리보기를 표시한다.
- 열려 있는 각 캔버스 탭은 자체 파일 경로와 clean/dirty 다이제스트(digest)를 가진 독립적인 문서다. `.chemvas` 로딩은 표준 단일 캔버스 페이로드만 허용한다.
- `.chemvas` 문서는 버전이 붙는다(현재 v4; v1–v3도 계속 로드 가능). v4는 결합을 컴팩트 배열로 저장한다: 삭제된 슬롯의 tombstone(v4 이전 파일의 `null` 항목)은 런타임 관리용이며 문서에는 더 이상 나타나지 않는다. 결합 identity는 런타임 범위다 — 문서의 어떤 섹션도 결합을 위치나 id로 참조하지 않는다(원자는 마크·링 채우기·그룹·perspective 상태가 참조하므로 명시적 id를 갖는다).

## 리팩토링 순서

현재 모듈화 순서, 완료 조건, 의존성 규칙은
[ADR 0001](adr/0001-feature-oriented-modularization.md)에서 관리한다.
