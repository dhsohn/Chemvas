# Refactoring / Test Coverage Report

작성일: 2026-04-17
최종 갱신: 2026-04-18

## 1. 현재 상태 요약

- 실행 기준: `pytest --cov=app --cov-report=term-missing`
- 결과: `812 passed in 11.94s`
- 전체 커버리지: `89%`
- 첫 보고서 시점 대비: `+414 tests`, `+18%p`

이번 라운드로 `InsertController` 1차 정리는 이미 끝났고, `SceneOpsController`도 delete/clipboard/transform/paste orchestration 대부분이 helper/service로 빠진 상태다. 직전 턴에는 `scene_item_access`를 추가해서 `core/history.py`, `SceneOpsController`, note 삭제 경로, delete tool scene-item 삭제 경로가 공통 controller-first fallback을 쓰도록 통일했고, `SceneOpsController`의 flip/paste apply도 `CanvasView` public wrapper 대신 이 access helper를 경유하도록 정리했다. 이후 `scene_item_access`를 ring/note/arrow/`ts_bracket`/orbital restore까지 확장했고, `canvas_document_state`의 document restore도 direct controller 참조 대신 같은 helper를 쓰도록 바꿨다. 최근에는 `atom_label_access`를 추가해 label-change 경로도 service-first fallback으로 통일했고, `structure_build_service`로 ring/chain/model build orchestration을 분리했다. 이번 턴에는 여기에 `_add_bond_between_points()`와 `add_benzene_ring()`의 mutation+history orchestration, `_sprout_regular_ring_from_atom()` / `_fuse_regular_ring_to_bond()` / `_fuse_chair_to_bond()`의 ring/template growth wrapper, `_sprout_bond_from_atom()` / `_sprout_benzene_from_atom()` / `_sprout_acetyl_from_atom()` / `_fuse_benzene_to_bond()`의 atom/bond growth orchestration, 그리고 `_benzene_ring_points()`의 attach-bond / attach-atom / free-placement resolution까지 `StructureBuildService`로 이동했다. `_sprout_bond_endpoint()` / `_regular_ring_points_for_atom()` / `_regular_ring_points_for_bond()` / `_template_points_for_bond()`에 이어 free benzene hexagon 계산도 `structure_geometry_logic` pure helper로 분리했다. 이어서 bond 기반 ring occupancy polygon lookup을 `ring_occupancy_logic`로 뺐고, benzene hover preview orchestration은 `BenzenePreviewService`로 이동시켜 `_ring_polygon_points_for_bond()`, `_clear_benzene_preview()`, `_render_benzene_preview()`를 shim으로 줄였다. 이번 추가 턴에서는 bond hover preview 조합도 `BondHoverPreviewService`로 이동시켜 `_add_bond_style_hover_preview()`, `_add_bond_tool_hover_preview()`, no-atoms bond hover preview 경로를 shim 수준으로 축소했다. `add_mark()` / `add_arrow()` / `add_ts_bracket()` / `add_orbital()`의 scene-decoration add flow는 `SceneDecorationService`로 이동했다. 현재는 `CanvasView 3696 stmts / 82%`, `SceneOpsController 184 stmts / 98%`, `SceneItemController 131 stmts / 99%`, `canvas_document_state 94%`, `scene_item_access 100%`, `core/tools.py 93%`로, 남은 주 타깃은 `CanvasView`의 나머지 large orchestration 표면과 일부 호환용 pass-through다.

## 2. 이번 라운드에서 완료된 작업

### 2.1 새로 추가된 모듈

- `app/ui/insert_smiles_transaction.py`
  - `load_smiles()`용 pre-clear snapshot 캡처
  - delete/add history command 조립
- `app/ui/insert_commit_service.py`
  - `SmilesCommitPlan` 실제 적용
  - `TemplateInsertResolution` 실제 적용
  - benzene special case / bond-merge path / free ring path 분리
- `app/core/text_tool_logic.py`
  - `TextTool` target resolution 추출
  - prompt 필요 여부와 initial value 결정 분리
  - created-atom `AddAtomsCommand` 생성 helper 추가
- `app/core/delete_tool_logic.py`
  - `DeleteTool` item kind별 삭제 dispatch 추출
  - drag erase history command 조립 분리
- `app/core/perspective_drag_logic.py`
  - `PerspectiveTool` rigid mode axis lock delta 해석 추출
  - zero-delta / unlock 규칙 분리
- `app/core/tool_overlay_logic.py`
  - overlay tool 공통 `NoDrag` activation 추출
  - preview item / handle cleanup 분리
- `app/core/bond_tool_logic.py`
  - `BondTool` press target precedence 분리
  - atom/bond snap target 판단 분리
  - endpoint angle/length snap 분리
- `app/ui/bond_graphics_logic.py`
  - bond graphics teardown / re-add 공통화
  - bond redraw 시 selection restore 계약 분리
  - connected bond redraw policy 공통화
- `app/ui/scene_delete_logic.py`
  - 선택 item 분류 추출
  - delete plan 생성 분리
  - single-bond fast path / mark filtering / handle-clear 판단 추출
- `app/ui/scene_delete_apply_logic.py`
  - delete plan 실제 적용 분리
  - bond/atom/scene-item 삭제 mutation과 history command assembly 추출
- `app/ui/scene_clipboard_logic.py`
  - selection -> clipboard payload serialize 분리
  - clipboard mime/custom-json/cache fallback candidate 추출
  - payload JSON decode / format-version 검증 분리
- `app/ui/scene_clipboard_transaction_logic.py`
  - copy render source / payload json / cache plan 분리
  - paste source bookkeeping / offset / pre-history snapshot plan 분리
- `app/ui/scene_transform_logic.py`
  - transform selection의 component/standalone grouping 분리
  - atom flip before/after/transformed position map 계산 분리
  - scene-item bounds / selection center 계산 분리
  - note / mark / orbital / `ts_bracket` / arrow flip state 변환 분리
- `app/ui/scene_transform_apply_logic.py`
  - transform component apply / command assembly 분리
  - standalone item apply / command assembly 분리
- `app/ui/scene_paste_apply_logic.py`
  - clipboard payload apply loop 분리
  - atom remap / added scene items 결과 object 추출
- `app/ui/scene_item_access.py`
  - scene-item create / restore / remove / apply / mark restore controller-first fallback 공통화
  - ring / note / arrow / `ts_bracket` / orbital restore access layer 추가
- `app/ui/atom_label_access.py`
  - atom label apply service-first fallback 공통화
  - `CanvasView` public wrapper와 `_atom_label_service` 사이 access layer 추가
- `app/ui/structure_build_service.py`
  - ring/chain/model structure build orchestration 추출
  - regular/hetero ring template, fused benzene, crown ether build 분리
  - hetero atom label apply / implicit carbon dot restore 경로 분리
  - fragment/template public method용 `run_recorded_build()` 추가
  - history snapshot / smiles reset / additions record wrapper 공통화
  - `_add_bond_between_points()` orchestration 분리
  - `add_benzene_ring()` mutation/history orchestration 분리
  - atom sprout / bond fuse ring-template wrapper 분리
  - chair fuse의 mirrored template/history wrapper 분리
  - bond/benzene/acetyl sprout orchestration 분리
  - benzene fuse midpoint wrapper 분리
  - benzene ring point resolution과 blocked-center fallback 분리
- `app/ui/scene_decoration_service.py`
  - `add_mark()` / `add_arrow()` / `add_ts_bracket()` / `add_orbital()`의 scene 등록 + history push 분리
  - `AddSceneItemsCommand` 생성 공통화
  - orbital restore 후 history 기록 경계 분리
- `app/ui/ring_occupancy_logic.py`
  - bond가 속한 ring polygon lookup 분리
  - point-in-ring occupancy 판단 분리
- `app/ui/benzene_preview_service.py`
  - benzene hover preview clear/render orchestration 분리
  - preview inner double-bond item factory 경계 분리
- `app/ui/bond_hover_preview_service.py`
  - bond style hover preview 조합 분리
  - atom-start / free-start bond hover preview 조합 분리
- `app/ui/structure_geometry_logic.py`
  - cyclic sprout endpoint 계산 분리
  - atom/bond attach ring point 계산 분리
  - bond template projection의 model lookup / merge packaging 분리
  - free benzene ring hexagon 계산 분리
- `app/ui/canvas_document_state.py`
  - document restore가 direct controller 참조 대신 공통 access helper를 사용하도록 정리
  - pre/post model scene-item restore 경계 단순화
- `app/ui/scene_single_item_mutation_logic.py`
  - `delete_atom()` / `delete_bond()` / `delete_ring()` history command 조립 분리
  - `flip_bond_direction()` / `apply_bond_style()` / `cycle_bond_style()` mutation + history 기록 분리

### 2.2 리팩터링된 영역

- `app/ui/insert_controller.py`
  - `load_smiles()`에서 snapshot/history 조립 제거
  - `_commit_smiles_insert()`에서 atom/bond apply loop 제거
  - `_commit_template_insert()`에서 benzene / merge / free ring mutation loop 제거
  - 현재 역할은 plan 계산, request/resolve, cancel/wiring 중심으로 축소
- `app/core/tools.py`
  - `TextTool.on_mouse_press()`에서 target resolution과 created-atom command 생성 제거
  - `TextTool.on_mouse_press()`에서 prompt 필요 여부와 initial value 결정 제거
  - `TextTool` label apply가 `CanvasView` public wrapper 대신 공통 `atom_label_access`를 사용하도록 정리
  - `DeleteTool._erase_at_event()`에서 item kind별 삭제 분기 제거
  - `DeleteTool.on_mouse_release()`에서 history wrapping 로직을 helper로 이동
  - `PerspectiveTool.on_mouse_move()`에서 axis lock 상태기계 제거
  - `_PreviewDragTool._clear_preview()`에서 preview teardown 제거
  - `TransformTool.deactivate()`와 일반 item press path에 handle cleanup 추가
  - 여러 tool의 `activate()`에서 공통 `NoDrag` activation helper 사용
  - `BondTool.on_mouse_press()`에서 existing bond target resolution 제거
  - `BondTool._snap_to_atom()`에서 atom/bond snap 판단 제거
  - `BondTool._snap_endpoint()`에서 endpoint angle/length snap 제거
- `app/ui/scene_ops_controller.py`
  - `delete_atom()` / `delete_bond()` / `delete_ring()`의 단건 history command assembly 제거
  - `flip_bond_direction()` / `apply_bond_style()` / `cycle_bond_style()`의 bond mutation/history 분리
  - `_rebuild_bond_graphics()`가 공통 helper를 사용하도록 정리
  - `delete_selected_items()`에서 selection classification 제거
  - `delete_selected_items()`에서 delete plan 생성 제거
  - `delete_selected_items()`에서 delete apply / command assembly 제거
  - `_selection_payload_for_clipboard()`에서 payload serialize 제거
  - `_clipboard_selection_payload()`에서 candidate/decode 규칙 제거
  - `copy_selection_to_clipboard()`에서 copy render/source/cache bookkeeping plan 제거
  - `flip_selected_items()`에서 transform grouping 제거
  - `flip_selected_items()`에서 atom flip map 계산 제거
  - `flip_selected_items()`에서 scene-item bounds/center/state 계산 제거
  - `flip_selected_items()`에서 transform apply / command assembly 제거
  - `paste_selection_from_clipboard()`에서 source bookkeeping / offset / pre-history snapshot plan 제거
  - `paste_selection_from_clipboard()`에서 atom/bond/scene-item apply loop 제거
  - flip/paste apply에서 `CanvasView` public scene-item wrapper 대신 공통 access helper 경유
  - controller는 clipboard bookkeeping, selection restore, 실제 canvas mutation / history 조립 위주로 축소
- `app/ui/canvas_view.py`
  - `_redraw_bond()`가 공통 bond graphics helper를 사용하도록 정리
  - bond style/flip redraw에서 selection 유지 계약을 controller와 공유
  - unused private transform wrapper 제거
  - `flip_horizontal()` / `flip_vertical()`가 controller로 직접 위임되도록 정리
  - label clear/prompt 내부 orchestration이 public wrapper self-call 대신 `_atom_label_service`를 직접 사용하도록 정리
  - structure build 저수준 orchestration이 공통 `StructureBuildService`를 사용하도록 정리
  - ring/template/model render helper가 service delegation wrapper로 축소
  - fragment/template public method의 history wrapper가 `StructureBuildService.run_recorded_build()`로 통일
  - chair/boat, hetero rings, fused benzenes, crown ethers, alkyl/functional fragments의 snapshot boilerplate 제거
  - `_add_bond_between_points()`와 `add_benzene_ring()`가 service delegation wrapper로 축소
  - `_benzene_ring_points()`가 service delegation wrapper로 축소
  - `_ring_polygon_points_for_bond()`가 occupancy helper delegation wrapper로 축소
  - `_clear_benzene_preview()` / `_render_benzene_preview()`가 preview service delegation wrapper로 축소
  - `_add_bond_style_hover_preview()` / `_add_bond_tool_hover_preview()`와 no-atoms bond hover preview 경로가 hover preview service 경유로 축소
  - `_sprout_regular_ring_from_atom()` / `_fuse_regular_ring_to_bond()` / `_fuse_chair_to_bond()`가 service delegation wrapper로 축소
  - `_sprout_bond_from_atom()` / `_sprout_benzene_from_atom()` / `_sprout_acetyl_from_atom()` / `_fuse_benzene_to_bond()`가 service delegation wrapper로 축소
  - `_sprout_bond_endpoint()` / `_regular_ring_points_for_atom()` / `_regular_ring_points_for_bond()` / `_template_points_for_bond()`가 pure helper adapter로 축소
  - ring fill item 생성만 canvas helper로 남기고 mutation/history 흐름은 service로 이동
  - `add_mark()` / `add_arrow()` / `add_ts_bracket()` / `add_orbital()`가 `SceneDecorationService` delegation wrapper로 축소
- `app/core/history.py`
  - scene-item history command가 공통 `scene_item_access` helper를 사용하도록 정리
  - create / restore / remove / apply / mark restore 경로를 controller-first access layer로 통일
  - `ChangeAtomLabelCommand`가 공통 `atom_label_access` helper를 사용하도록 정리
- `app/ui/canvas_note_controller.py`
  - note focus-out 삭제 경로가 공통 `scene_item_access` helper를 사용하도록 정리
- `app/core/delete_tool_logic.py`
  - erase scene-item 삭제 경로가 공통 `scene_item_access` helper를 사용하도록 정리
- `app/ui/structure_insert_service.py`
  - inserted atom label apply가 `CanvasView` public wrapper 대신 공통 `atom_label_access`를 사용하도록 정리
- `app/ui/insert_commit_service.py`
  - smiles commit label apply가 `CanvasView` public wrapper 대신 공통 `atom_label_access`를 사용하도록 정리

### 2.3 새로 추가되거나 강화된 테스트

- `tests/test_atom_label_access.py`
- `tests/test_structure_build_service.py`
- `tests/test_structure_geometry_logic.py`
- `tests/test_ring_occupancy_logic.py`
- `tests/test_benzene_preview_service.py`
- `tests/test_bond_hover_preview_service.py`
- `tests/test_scene_decoration_service.py`
- `tests/test_bond_graphics_logic.py`
- `tests/test_insert_smiles_transaction.py`
- `tests/test_insert_commit_service.py`
- `tests/test_insert_controller.py` 추가 보강
- `tests/test_text_tool_logic.py`
- `tests/test_delete_tool_logic.py`
- `tests/test_perspective_drag_logic.py`
- `tests/test_tool_overlay_logic.py`
- `tests/test_bond_tool_logic.py`
- `tests/test_tools_additional.py` 추가 보강
- `tests/test_gui_smoke.py` 추가 보강
- `tests/test_scene_delete_logic.py`
- `tests/test_scene_delete_apply_logic.py`
- `tests/test_scene_clipboard_logic.py`
- `tests/test_scene_clipboard_transaction_logic.py`
- `tests/test_scene_single_item_mutation_logic.py`
- `tests/test_scene_transform_logic.py`
- `tests/test_scene_transform_apply_logic.py`
- `tests/test_scene_paste_apply_logic.py`
- `tests/test_core_history.py` 추가 보강
- `tests/test_scene_item_controller.py` 추가 보강
- `tests/test_canvas_note_controller_unit.py` 추가 보강
- `tests/test_scene_item_access.py`
- `tests/test_canvas_document_state.py`
- `tests/test_tools_unit.py` 추가 보강
- `tests/test_structure_insert_service.py` 추가 보강
- `tests/test_canvas_view_additional.py` 추가 보강

강화된 포인트:

- `load_smiles()` history subcommand 순서와 payload 고정
- free mark vs attached mark 분리 검증
- `build_command() is None`일 때 `_push_command` 미호출 보장
- smiles commit / template commit apply helper의 성공 및 실패 경로 검증
- `TextTool` invalid hover bond id fallback 검증
- dialog cancel / created-atom command metadata 검증
- `DeleteTool` single delete / multi delete history wrapping 검증
- atom / bond / ring / scene item 삭제 dispatch contract 고정
- `PerspectiveTool` rigid axis lock, unlock, zero-delta 규칙 고정
- overlay helper의 preview removal / handle cleanup / `RuntimeError` 방어 검증
- `ToolController` switch 경유 arrow preview cleanup contract 고정
- `TransformTool` 일반 item click / deactivate cleanup 경로 고정
- `BondTool` press target precedence와 snap fallback contract 고정
- `BondTool` endpoint snap contract 고정
- `TextTool` whitespace prompt의 existing/new target contract 고정
- `CanvasView.set_tool()` 경유 `arrow` / `ts_bracket` preview teardown smoke 고정
- tool switch 뒤 stale mouse release가 old preview tool commit으로 이어지지 않는 GUI contract 고정
- `scene_delete_logic`의 selection buckets / delete plan helper contract 고정
- `scene_delete_apply_logic`의 bond reverse-order delete / atom mark snapshot / scene-item delete contract 고정
- `scene_clipboard_logic`의 payload serialize / mime fallback / decode contract 고정
- `scene_clipboard_transaction_logic`의 copy source/payload/cache plan, paste count/offset/snapshot plan contract 고정
- `scene_single_item_mutation_logic`의 단건 delete / bond style mutation / history callback contract 고정
- `bond_graphics_logic`의 selection restore / connected redraw contract 고정
- `scene_transform_logic`의 grouping / atom flip map / bounds / center / scene-item state helper contract 고정
- `scene_transform_logic`의 invalid note bounds / unknown state / missing atom fallback / duplicate standalone edge branch 고정
- `scene_transform_apply_logic`의 component/standalone apply command contract 고정
- `scene_paste_apply_logic`의 atom remap / bond restore / translated scene-item apply contract 고정
- `CanvasView` flip wrapper가 private helper가 아니라 controller에 직접 위임된다는 계약 고정
- `core/history`가 scene-item history mutation에서 controller 경로를 우선 사용한다는 계약 고정
- `SceneItemController`의 attached/deleted no-op, non-note registry 등록, scene lookup failure cleanup branch 고정
- `SceneItemController`의 `_restore_*` helper와 `create_scene_item_from_state()` valid/invalid path 고정
- ring bond-id lookup의 short/non-int sequence 방어 고정
- `SceneItemController.remove_scene_item()`의 off-scene/off-registry/no-op branch arc 고정
- note/delete/scene-ops 삭제 경로의 controller-first fallback 고정
- 공통 `scene_item_access` helper의 controller-first / canvas fallback contract 고정
- 공통 `atom_label_access` helper의 service-first / canvas wrapper fallback contract 고정
- `document restore`가 controller 경로와 `CanvasView` wrapper fallback 경로 모두에서 호환된다는 smoke 고정
- `core/tools.py` wrapper-only false/no-op branch 고정
- `StructureInsertService`, `InsertCommitService`, `TextTool`, `ChangeAtomLabelCommand`의 label apply가 service-first access layer를 우선 사용한다는 contract 고정
- `CanvasView.clear_atom_label()` / `prompt_atom_label()` / `_restore_atom_from_state()`가 `_atom_label_service` 직통 경로를 사용한다는 smoke 고정
- `StructureBuildService`의 ring/chain/model render contract 고정
- `CanvasView` structure build wrapper가 `StructureBuildService` delegation shim으로 동작한다는 smoke 고정
- `StructureBuildService.run_recorded_build()`의 history snapshot / added-scene-items contract 고정
- representative fragment/template public method가 공통 recorded-build helper를 경유한다는 smoke 고정
- `StructureBuildService.add_bond_between_points()`의 create/update/record contract 고정
- `StructureBuildService.add_benzene_ring()`의 bond/ring-item/additions contract 고정
- `StructureBuildService.benzene_ring_points()`의 attach precedence / blocked-center / free fallback contract 고정
- `ring_occupancy_logic`의 polygon lookup / deleted-item skip / point-in-ring contract 고정
- `BenzenePreviewService`의 clear/render preview orchestration contract 고정
- `BondHoverPreviewService`의 style/tool/free hover preview orchestration contract 고정
- `StructureBuildService.sprout/fuse ring-template helper`의 record/no-op contract 고정
- `StructureBuildService.sprout bond/benzene/acetyl + fuse benzene helper`의 direct contract 고정
- `structure_geometry_logic`의 sprout endpoint / ring attach / template projection / free benzene geometry contract 고정
- `CanvasView._add_bond_between_points()` / `add_benzene_ring()`가 service delegation shim으로 동작한다는 smoke 고정
- `CanvasView._benzene_ring_points()`가 service delegation shim으로 동작한다는 smoke 고정
- `CanvasView._ring_polygon_points_for_bond()`가 occupancy helper delegation shim으로 동작한다는 smoke 고정
- `CanvasView._clear_benzene_preview()` / `_render_benzene_preview()`가 preview service delegation shim으로 동작한다는 smoke 고정
- `CanvasView._add_bond_style_hover_preview()` / `_add_bond_tool_hover_preview()`가 hover preview service delegation shim으로 동작한다는 smoke 고정
- `CanvasView._sprout_regular_ring_from_atom()` / `_fuse_regular_ring_to_bond()` / `_fuse_chair_to_bond()`가 service delegation shim으로 동작한다는 smoke 고정
- `CanvasView._sprout_bond_from_atom()` / `_sprout_benzene_from_atom()` / `_sprout_acetyl_from_atom()` / `_fuse_benzene_to_bond()`가 service delegation shim으로 동작한다는 smoke 고정
- `CanvasView` geometry helper wrapper가 pure helper 결과를 `QPointF`/merge로 adapter한다는 smoke 고정
- `SceneDecorationService.add_mark()` / `add_arrow()` / `add_ts_bracket()` / `add_orbital()` contract 고정
- `CanvasView.add_mark()` / `add_arrow()` / `add_ts_bracket()` / `add_orbital()`가 service delegation shim으로 동작한다는 smoke 고정

## 3. 현재 우선 점검 대상

| 영역 | 규모 / 커버리지 | 근거 | 판단 |
| --- | --- | --- | --- |
| `app/ui/canvas_view.py` | `3696 stmts / 82%` | bond/benzene + scene-decoration add + sprout/fuse growth wrapper와 geometry helper adapter, benzene point resolver, preview/occupancy shim, bond hover preview shim까지 빠졌지만 여전히 가장 큰 파일이다 | 지금 바로 이어갈 1순위 |
| `app/core/tools.py` | `828 stmts / 93%` | 구조 추출과 wrapper-only branch polish가 대부분 끝났고 남은 건 소수 예외 경로다 | 낮은 우선순위 |
| `app/ui/scene_item_controller.py` | `131 stmts / 99%` | helper/controller 경계는 사실상 안정화됐고 남은 건 미세 branch arc 수준이다 | 급하지 않음 |
| `app/ui/canvas_document_state.py` | `78 stmts / 94%` | document restore는 access layer로 정리됐고 smoke도 들어가서 현재는 유지 단계다 | 급하지 않음 |
| `app/ui/structure_build_service.py` | `288 stmts / 88%` | structure build와 recorded-build, bond/benzene mutation, atom/bond sprout, ring/template fuse wrapper, benzene point resolver가 service로 모였다 | 중간 우선순위 |
| `app/ui/structure_geometry_logic.py` | `102 stmts / 85%` | geometry lookup/packaging에 free benzene hexagon까지 분리됐고 남은 miss는 invalid/default 세부 분기다 | 중간 우선순위 |
| `app/ui/main_window.py` | `1306 stmts / 84%` | 툴바 wiring과 theme 적용이 여전히 크고 inline 연결이 많다 | 중간 우선순위 |
| `app/core/rdkit_conversion.py` | `464 stmts / 84%` | user-visible failure branch가 많고 남은 miss가 분기 밀집 구간에 모여 있다 | targeted test 보강 후보 |
| `app/ui/scene_transform_logic.py` | `184 stmts / 99%` | transform helper는 사실상 안정화됐고 남은 miss는 note vertical valid-rect 정도다 | 급하지 않음 |
| `app/ui/scene_ops_controller.py` | `184 stmts / 98%` | orchestration controller로 거의 정리됐고 남은 리팩토링 ROI가 낮다 | 급하지 않음 |
| `app/ui/insert_controller.py` | `184 stmts / 93%` | 1차 분리 완료, 남은 건 failure-path polishing 수준 | 급하지 않음 |

## 4. 리팩토링 권장 사항

### 4.1 `InsertController`는 이번 라운드 목표를 달성했다

이제 `InsertController`는 최우선 분리 대상이 아니다.

- `load_smiles()` transaction builder 분리 완료
- smiles/template commit apply service 분리 완료
- controller는 plan 계산과 session cleanup 중심으로 축소

남은 일은 구조 추출보다 polish 쪽이다.

- commit failure-path branch 추가 테스트
- helper/service naming 정리
- 필요 시 `InsertCommitService`를 smiles/template 별 모듈로 더 쪼개기

### 4.2 `core/tools.py`는 1차 구조 목표를 거의 달성했다

첫 번째로 손댄 `TextTool` 경계, `DeleteTool` 삭제 규칙, `PerspectiveTool` 축 잠금 상태기계, temporary overlay cleanup, `BondTool` fallback/snap 규칙, `TextTool` input planning은 이미 빠졌고, preview 계열 GUI switch smoke와 wrapper-only false/no-op branch도 이번에 대부분 정리됐다. 이제 남은 건 대형 구조 추출이 아니라 드문 예외 경로 유지 수준이다.

- 대표 hotspot
  - `TransformTool.on_mouse_press()` at `app/core/tools.py:931`
  - `ToolController.set_active()` 경유 cleanup contract
  - 일부 wrapper branch와 예외 경로

이번 라운드에서 이미 정리된 부분:

- target atom / snapped position 해석
- created-atom `AddAtomsCommand` 생성
- `DeleteTool` 삭제 규칙 dispatch
- `DeleteTool` history wrapping
- `PerspectiveTool` rigid axis lock delta 해석
- overlay tool 공통 `NoDrag` activation
- preview item / handle cleanup lifecycle
- `BondTool` existing bond target precedence
- `BondTool` atom/bond snap target 판단
- `BondTool` endpoint angle/length snap
- `TextTool` prompt 필요 여부와 initial value 결정
- preview tool의 `CanvasView` 레벨 switch cleanup smoke
- preview tool switch 뒤 stale release no-op contract

권장 방향:

- 다음은 `CanvasView`의 transform/scene-item pass-through와 orchestration 표면을 한 번 더 줄이는 편이 ROI가 가장 크다
- `core/tools.py`는 이후 실패 branch 몇 개를 보강하는 정도면 충분하다

### 4.3 `SceneOpsController`는 delete/clipboard/transform + delete/paste apply + clipboard transaction + 단건 mutation helper + flip scene-item helper 단계를 통과했다

이 영역은 이미 전용 테스트가 충분하고, 이번 라운드에서 `delete_selected_items()`의 selection classification + delete plan 생성, delete apply / command assembly, clipboard payload serialize/deserialize, copy/paste clipboard transaction plan, `flip_selected_items()`의 selection grouping + atom flip map 계산, scene-item bounds/center/state 계산, transform apply / command assembly, `paste_selection_from_clipboard()`의 actual apply loop, `delete_atom()` / `delete_bond()` / `delete_ring()`과 bond update 계열의 단건 mutation, bond redraw/selection restore 공통화까지 먼저 빠졌다. 이제 controller 자체는 얇은 orchestration 경계로 사실상 정리된 상태다.

- `delete_selected_items()` at `app/ui/scene_ops_controller.py:118`
- `flip_selected_items()` at `app/ui/scene_ops_controller.py:205`
- `_selection_payload_for_clipboard()` at `app/ui/scene_ops_controller.py:297`
- `copy_selection_to_clipboard()` at `app/ui/scene_ops_controller.py:345`
- `paste_selection_from_clipboard()` at `app/ui/scene_ops_controller.py:396`

권장 방향:

- 완료: `delete_selected_items()`의 selection classification + delete plan 생성 분리
- 완료: `delete_selected_items()`의 delete apply 단계 service 승격
- 완료: clipboard payload serialize/deserialize 분리
- 완료: `copy_selection_to_clipboard()`와 `paste_selection_from_clipboard()`의 clipboard transaction plan 분리
- 완료: `flip_selected_items()`의 selection grouping + atom flip map 계산 분리
- 완료: `flip_selected_items()`의 scene-item bounds / center / state 변환 분리
- 완료: `flip_selected_items()`의 scene-item apply / command assembly 분리
- 완료: `paste_selection_from_clipboard()`의 paste apply 단계 service 승격
- 완료: `delete_atom()` / `delete_bond()` / `delete_ring()`과 bond update 계열의 단건 mutation helper 정리
- 완료: bond redraw / selection restore helper 공통화
- 완료: `core/history.py`의 scene-item wrapper 의존을 controller-first adapter로 축소
- 완료: 공통 `scene_item_access` helper로 controller-first fallback 통일
- 완료: `SceneOpsController` flip/paste apply의 `CanvasView` wrapper 의존 축소
- 다음: 남은 `CanvasView` public scene-item wrapper 의존을 타는 실제 협력 지점 검토
- 완료: `SceneItemController` restore helper / create path branch 보강
- 완료: `SceneItemController.remove_scene_item()`의 주요 branch arc 정리
- 그 다음: `CanvasView` public scene-item wrapper를 타는 나머지 fallback 협력 지점 검토
- 이후 `SelectionDeleteService`
- `SelectionTransformService`
- `ClipboardSelectionService`

controller는 canvas collaborator 연결만 담당하는 얇은 조정자로 남긴다.

### 4.4 `CanvasView`는 하위 모듈 정리 이후 2차 축소로 접근하기

현재 `CanvasView`에서 이미 빠져나간 책임은 다음과 같다.

- `AtomLabelService`
- `StructureInsertService`
- `SelectionRotationController`
- `InsertController` 내부 helper/service들
- `bond_graphics_logic`를 통한 bond redraw / selection restore 공통 규칙
- `scene_transform_logic`를 통한 flip bounds / center / scene-item state 규칙

따라서 다음 `CanvasView` 작업은 독립 대형 추출이 아니라, 하위 모듈 정리 이후 pass-through와 orchestration 표면을 한 번 더 줄이는 것이다.

이번 턴까지 반영된 추가 정리:

- `canvas_document_state.restore_document_pre_model_items()` / `restore_document_post_model_items()`가 direct controller 참조 대신 `scene_item_access` 경유
- `document restore`의 controller 경로 / `CanvasView` wrapper fallback 경로 smoke 고정
- `CanvasView.add_mark()` / `add_arrow()` / `add_ts_bracket()` / `add_orbital()`가 `SceneDecorationService` 경유
- `CanvasView._benzene_ring_points()`와 `StructureBuildService.add_benzene_ring()`이 공통 service resolver를 공유
- `CanvasView._ring_polygon_points_for_bond()`가 `ring_occupancy_logic` 경유
- `CanvasView._clear_benzene_preview()` / `_render_benzene_preview()`가 `BenzenePreviewService` 경유
- `CanvasView._add_bond_style_hover_preview()` / `_add_bond_tool_hover_preview()`와 no-atoms bond preview 경로가 `BondHoverPreviewService` 경유

이제 남은 `CanvasView` scene-item pass-through는 대부분 일부 테스트/협력자 호환용 public 표면과 `CanvasView` 본체의 wrapper 정의 자체다. 다음 축소는 history/document restore처럼 실제 협력 지점에서 access layer를 더 쓰게 하거나, wrapper를 타는 외부 협력 경로를 더 줄이는 방향이 맞다.

### 4.5 `MainWindow`와 `RDKitConversion`은 여전히 후순위다

- `MainWindow`: descriptor 기반 toolbar/theme 정리
- `RDKitConversion`: 구조 개편보다 실패 branch test 보강

둘 다 중요하지만, 현재 구조 리스크 대비 우선순위는 `core/tools.py`와 `SceneOpsController`보다 낮다.

## 5. 테스트 커버리지 확장 권장안

### 5.1 가장 먼저 늘릴 테스트

#### `SceneOpsController`

- clipboard payload mismatch 세부 변종
- orchestration smoke와 selection restore 정도만 유지하면 충분하다

#### `CanvasView`

- scene-item wrapper fallback 협력 지점 추가 축소
- structure insert 후 selection 복원
- structure insert 시 title note 생성
- atom merge 후 duplicate bond 정리 우선순위
- carbon dot <-> explicit label 전환
- label change undo 기록
- `_redraw_bond()` caller 경유 selection 유지 smoke

#### `scene_transform_logic`

- note vertical valid-rect path

#### `core/tools.py`

- drag erase 누적 command 같은 드문 GUI 예외 경로
- 일부 미사용 base/default path 정도만 유지 보강

### 5.2 그 다음으로 늘릴 테스트

#### `SceneItemController`

- rare fallback arc 정도만 유지
- ring 관련 geometry refresh 호출 누락 방지

#### `RDKitConversionHelper`

- 오류 메시지 포맷
- unsupported combination branch
- multi-component layout edge case

## 6. 유지하는 편이 좋은 영역

아래 영역은 현재 구조와 테스트 균형이 좋다. 계속 기준점으로 삼기 좋다.

- `app/core/history.py`
- `app/core/template_geometry.py`
- `app/core/document_io.py`
- `app/core/rdkit_adapter.py`
- `app/ui/template_insert_logic.py`
- `app/ui/smiles_insert_logic.py`
- `app/ui/selection_hit_logic.py`
- `app/ui/atom_label_service.py`
- `app/ui/structure_insert_service.py`
- `app/ui/selection_rotation_controller.py`
- `app/ui/insert_smiles_transaction.py`
- `app/ui/insert_commit_service.py`
- `app/core/bond_tool_logic.py`
- `app/core/text_tool_logic.py`
- `app/core/perspective_drag_logic.py`
- `app/core/tool_overlay_logic.py`
- `app/ui/scene_delete_logic.py`
- `app/ui/scene_delete_apply_logic.py`
- `app/ui/scene_clipboard_logic.py`
- `app/ui/scene_clipboard_transaction_logic.py`
- `app/ui/scene_single_item_mutation_logic.py`
- `app/ui/bond_graphics_logic.py`
- `app/ui/scene_transform_logic.py`
- `app/ui/scene_transform_apply_logic.py`
- `app/ui/scene_paste_apply_logic.py`
- `app/ui/scene_decoration_service.py`

공통점:

- 책임 경계가 선명하다.
- 순수 로직 또는 얇은 service 형태다.
- 테스트 계약이 이미 비교적 단단하다.

## 7. 권장 실행 순서

1. `CanvasView`의 남은 add/mutation orchestration과 pass-through 표면을 한 번 더 줄인다.
2. `scene_transform_logic`의 남은 edge branch를 direct test로 보강한다.
3. `core/tools.py` wrapper branch를 targeted polish 한다.
4. `MainWindow`, `RDKitConversion`을 순서대로 다듬는다.

## 8. 결론

첫 보고서에서 제시한 방향은 여전히 맞다. 다만 이번 라운드로 `InsertController`는 더 이상 주 병목이 아니고, `core/tools.py`도 첫 추출이 사실상 마무리 단계에 들어갔다. transaction builder, commit service, text-tool helper, delete-tool helper, perspective-drag helper, tool-overlay helper, bond-tool helper, preview tool GUI smoke에 이어 `SceneOpsController` delete helper, delete apply helper, clipboard helper, clipboard transaction helper, transform helper, transform apply helper, paste apply helper, 단건 mutation helper, bond redraw helper, flip scene-item bounds/center/state helper까지 들어간 상태라서, 다음 단계는 `SceneOpsController` 추가 분해보다 `CanvasView` 2차 축소와 `scene_transform_logic` edge branch 보강에 집중하는 것이다.

현재 총평:

- 방금 큰 구조 추출이 끝난 곳: `InsertController`, `core/tools.py` 1차 정리
- 이번에 닫은 항목: preview tool GUI smoke, `SceneOpsController` delete plan 분리, delete apply 분리, clipboard payload 분리, clipboard transaction 2차 분리, transform grouping/atom map 분리, transform apply/command assembly 분리, paste apply 분리, 단건 mutation helper 분리, bond redraw/selection restore 공통화, flip scene-item bounds/center/state helper 분리, `SceneDecorationService`를 통한 scene-decoration add/history 분리
- 지금 바로 손대야 할 곳: `CanvasView` 2차 축소
- 그 다음 targeted polish 후보: `scene_transform_logic`, `core/tools.py`
- 큰 리팩터링보다 targeted test 보강이 맞는 곳: `RDKitConversion`
