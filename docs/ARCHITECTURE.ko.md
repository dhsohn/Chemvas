# 아키텍처

## 책임 경계 (Responsibility Boundaries)
- CanvasView (`app/ui/canvas_view.py`): 입력 처리, 도구(tool) 디스패치, 선택 상태 관리, 그리고 모델/렌더/히스토리 업데이트의 조율을 담당한다. 저수준 드로잉 프리미티브(low-level drawing primitives)를 직접 소유해서는 안 된다.
- MoleculeModel (`app/core/model.py`): 순수한 원자/결합 데이터와 ID. Qt 의존성이 없다.
- RDKitAdapter (`app/core/rdkit_adapter.py`): SMILES 가져오기, 물성 계산, 3D 좌표 생성, 별칭(alias) 확장, 미리보기 씬(preview scene) 구성을 담당하는 선택적 화학 백엔드. UI 코드는 이를 필수 시작 의존성이 아니라 최선 노력(best-effort) 서비스로 취급해야 한다.
- Renderer (`app/core/renderer.py`): 스타일, 펜/브러시, 폰트 설정.
- HistoryCommand (`app/core/history.py`): 델타 기반 실행 취소/다시 실행(undo/redo). 다중 엔티티(multi-entity) 연산은 `CompositeCommand`로 그룹화되며, 이는 다시 실행 시 자식 델타 커맨드를 순서대로 적용하고 실행 취소 시 역순으로 적용한다.
- BondRenderer (`app/ui/bond_renderer.py`): 결합 QGraphicsItem 생성/업데이트 및 기하 헬퍼(geometry helpers)로, CanvasView 컨텍스트에 의해 구동된다.
- Graphics items (`app/ui/graphics_items.py`): 선택 불가능한 QGraphicsItem 래퍼(wrapper).
- Label layout (`app/ui/label_layout_logic.py`): 원자 레이블 원시 문자열을 조판 런(typographic runs, 아래첨자 포함)과 그 배치로 파싱하는 순수(Qt-free) 로직. 레이블 타이포그래피의 단일 진실 공급원(single source of truth)이다: `AtomLabelItem`은 화면 그리기를 위해 이를 소비하고, 벡터 내보내기(vector export)는 글리프를 아웃라인 처리할 때 동일한 배치를 소비하므로 화면과 내보내기가 결코 어긋나지 않는다. 표시 텍스트에 대해서만 동작하며 저장된 `element` 문자열을 절대 변경하지 않는다.
- Figure export (`app/ui/export_plan_logic.py` + `app/ui/export_dialog_logic.py` + `app/ui/export_render_service.py`): 두 개의 순수 모듈은 패딩이 적용된 소스 사각형(source rect) / 물리적 출력 크기(포인트 단위)를 계산하고 대화상자의 포맷/크기/경로 규칙을 소유한다. Qt 서비스(`export_scene`)는 보이는 콘텐츠 항목을 수집하고(일시적 오버레이는 클립보드 복사와 동일한 방식으로 제외), 항목별 내보내기 잉크/콘텐츠 사각형(export ink/content rects)이 가능한 경우 이를 사용해 경계를 계산하며(따라서 레이블 히트 타겟과 투명한 암시적 탄소 점(implicit-carbon dots)이 물리적 크기에 영향을 주지 않도록), 나머지 모든 것을 숨기고, 원자 레이블을 아웃라인 모드로 전환하며, 씬 영역을 네 가지 싱크(sink) 중 하나로 렌더링한다 — `QSvgGenerator`(72 dpi의 SVG로 1 단위 = 1 pt), `QPdfWriter`(PDF, 페이지가 콘텐츠에 맞춰 포인트 단위로 크기 설정), 또는 `QImage`(DPI 메타데이터가 포함된 PNG/TIFF). `unit_scale`(씬 단위당 포인트) 또는 `target_width_pt`는 줌과 무관하게 결정적인 물리적 크기를 제공한다: 결합 길이 모드(bond-length mode)는 스타일의 `bond_length_pt`를 사용하고, 컬럼 모드(column modes)는 84/174 mm에 맞춘다. `scope`는 전체 캔버스 대 선택 영역을 선택하고, `background`는 투명 대 흰색을 선택한다. 아웃라인 처리된 레이블은 어떤 포맷도 폰트 의존적인 `<text>`를 포함하지 않음을 의미하므로 화면/SVG/PDF/래스터 모두 동일한 글리프를 표시한다.

## UI 계층 규율 (ports / access / state / services)
`app/ui` 패키지는 역할이 고정된 다수의 작은 모듈로 의도적으로 분리되어 있다. 목표는 `CanvasView`와 `MainWindow`를 얇은 Qt 셸로 유지하고(갓 오브젝트 금지), 모든 서비스를 헤드리스로 생성 가능하게 하며(전체 테스트 스위트가 `SimpleNamespace` 캔버스로 약 20초에 실행), 모든 의존성을 명시적으로 만드는 것이다.

- **State 모듈** (`*_state.py`): 관심사당 dataclass 하나와 `<name>_state_for(canvas)` 접근자. 모든 상태 접근자는 `ensure_canvas_state(canvas, name, factory)`(`ui/canvas_state_lookup.py`)를 거치며, 조회와 부착에 하나의 이름만 사용한다. 실제 캔버스에서는 모든 상태가 eager 생성되는 `CanvasRuntimeState` 컨테이너(`ui/canvas_runtime_state.py`)의 필드로 존재한다. 컨테이너는 strict하다 — 컨테이너에 없는 필드를 요청하는 접근자는 그림자 사본을 조용히 부착하는 대신 즉시 실패한다. 일부 상태(`model`, `renderer`, `bond_renderer`, `rdkit`)는 의도적으로 캔버스 직접 속성으로 저장되며 `runtime_field=False`를 사용한다. 새 상태 추가 시: dataclass + 접근자 + `CanvasRuntimeState` 필드가 세트이며, `test_state_accessor_names_match_runtime_state_container`가 동기화를 강제한다.
- **Access 모듈** (`*_access.py`): 연산 하나를 감싸는 자유 함수(`foo_for(canvas)`). `canvas.services`에 직접 접근할 수 없고, 서비스 조회는 대응하는 ports 모듈에 위임한다.
- **Ports 모듈** (`*_ports.py`): 서비스 컨테이너(`canvas_services_for` / window 비공개 저장소)를 해석할 수 있는 유일한 모듈. 그 외 모든 코드는 협력자를 주입받거나 port를 호출한다.
- **서비스와 컨트롤러**: `ui/canvas_service_composer.py`에서 캔버스당 한 번, 명시적 키워드 주입으로 조립된다 — 서비스 내부의 서비스 로케이터 금지, 누락된 배선을 숨기는 `=None` 협력자 기본값 금지.
- **core는 Qt-free이자 ui-free**: `app/core`는 모듈 수준에서 `ui`를 import할 수 없다(지연 해석되는 프로토콜 구현이 유일한 승인된 예외, `core/history.py` 참고).

이 규칙들은 `tests/test_architecture_boundaries.py`가 강제한다. 이 파일은 *규칙*(금지 접근 패턴, 제거된 표면의 유지, 의존성 계약)만 담는다 — 특정 구현 문구가 존재한다는 단언은 두지 않는다. 규칙을 추가할 때는 새 코드가 자동으로 적용받는 패턴 금지 또는 의존성 계약으로 표현한다.

이 규율의 알려진 트레이드오프(의도적으로 수용): 실재하는 간접 비용(ui LOC의 약 20%가 배선)과 캔버스 seam의 약한 정적 타이핑(`canvas: Any`). 하나의 불변식이 여러 작은 모듈에 걸칠 때는 일관성 계약을 소유 모듈 한 곳에 문서화해야 한다 — 파생 그래프 인덱스의 예로 `ui/graph_index_operations.py`와 `CanvasGraphService.bond_id_between_with_repair` 패턴을 참고.

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

## 계획된 다음 슬라이스 (Planned Next Slices)
- 미리보기 렌더링(결합/SMILES/템플릿)을 전용 렌더러 모듈로 추출.
- 다중 항목 연산(선택, 대량 이동, 템플릿 삽입) 주위의 씬 업데이트를 배치(batch) 처리.
- 출판용 내보내기(publication export)가 도입됨(`export_scene`): SVG/PDF/PNG/TIFF, 아웃라인 레이블, 포맷/범위/DPI/배경 대화상자, 물리적 단위 크기 조정(결합 길이 + 84/174 mm 컬럼 맞춤). 이 경로의 다음 작업:
- 클립보드 벡터(Clipboard vector): 클립보드에 PDF/SVG 형식도 함께 배치(현재는 PNG만 복사됨)하여 Illustrator / macOS Office로 붙여넣기 시 벡터를 유지.
- 형식 전하를 레이블 위첨자(superscript)로 접기(`place_runs`가 이미 `super` 역할을 지원함); 인라인 텍스트를 파싱하는 대신 기존 전하 마크/속성을 사용해 인라인 전하 대 아래첨자 모호성을 해결.
