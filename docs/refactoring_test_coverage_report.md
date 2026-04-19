# Refactoring / Test Coverage Report

작성일: 2026-04-17
최종 갱신: 2026-04-19

## 1. 현재 상태 요약

- 실행 기준: `pytest --cov=app --cov-report=term-missing`
- 결과: `1196 passed in 14.18s`
- 전체 커버리지: `99%`
- 첫 보고서 시점 대비: `+798 tests`, `+28%p`

이번 턴에는 [test_graphics_items.py](/Users/daehyupsohn/LiteDraw/tests/test_graphics_items.py), [test_structure_benzene_logic.py](/Users/daehyupsohn/LiteDraw/tests/test_structure_benzene_logic.py), [test_bond_graphics_logic.py](/Users/daehyupsohn/LiteDraw/tests/test_bond_graphics_logic.py), [test_template_insert_logic.py](/Users/daehyupsohn/LiteDraw/tests/test_template_insert_logic.py), [test_benzene_preview_service.py](/Users/daehyupsohn/LiteDraw/tests/test_benzene_preview_service.py)를 보강해 `graphics_items`, `structure_benzene_logic`, `bond_graphics_logic`, `template_insert_logic`, `benzene_preview_service`의 남은 guard/fallback branch를 모두 닫았다. 그 결과 이번에 지정한 다섯 모듈은 모두 `100%`까지 올라왔고, 다음 우선순위는 `preview_scene_renderer`, `scene_clipboard_logic`, `scene_delete_logic`, `canvas_move_controller`, `text_tool_logic` 같은 95%대 tail이다.

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
  - chair/boat fragment template public builder 이동
  - fused heterocycle (`indole` / `quinoline` / `isoquinoline` / `benzimidazole`) builder 이동
  - phenyl/benzyl/vinyl/allyl/carboxyl/nitro/sulfonyl/carbonyl/tBu/iPr/Me/Et builder 이동
  - `add_peptide_2()`의 chain + carbonyl oxygen label orchestration 이동
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
- `app/ui/mark_hover_preview_service.py`
  - mark hover preview key 계산과 atom/free 분기 분리
  - mark hover preview item 배치 orchestration 분리
- `app/ui/hover_highlight_logic.py`
  - hover highlight hit/preview decision 분리
  - atom/bond/free preview clear/no-op 판단 분리
- `app/ui/hover_scene_service.py`
  - hover item clear / preview add / atom/bond indicator scene mutation 분리
  - `hover_items`, `hover_atom_id`, `hover_bond_id`, `_hover_preview_style` lifecycle 공통화
- `app/ui/hover_interaction_service.py`
  - hover hit lookup / preview key 계산 / apply orchestration 분리
  - `hover_highlight_logic`와 hover preview/scene service 연결 경계 정리
- `app/ui/canvas_graph_service.py`
  - bond adjacency / bond index / graph-version cache lifecycle 분리
  - connected component / cycle / rotatable-axis / rotation-hint heuristic 분리
  - bond-set classify / connected-atom expansion helper 분리
- `app/ui/canvas_bond_mutation_service.py`
  - duplicate bond no-op / new-bond index registration 분리
  - sparse bond-list restore / endpoint rewire / graphics cleanup 분리
  - trim/remove 시 adjacency/index/spatial invalidation lifecycle 분리
- `app/ui/canvas_atom_mutation_service.py`
  - atom add/remove/restore/color orchestration 분리
  - atom graphics cleanup, neighbor/bond-id rewire, spatial invalidation lifecycle 분리
  - carbon dot / explicit carbon label / non-carbon label apply 분기 분리
- `app/ui/canvas_color_mutation_service.py`
  - bond/atom/ring color mutation과 ring-fill history command assembly 분리
  - ring-selected atom/bond 재귀 recolor와 scene-item color update 경계 분리
- `app/ui/canvas_document_session_service.py`
  - snapshot/restore/save/load document session orchestration 분리
  - history disable/reenable와 history reset 경계 분리
- `app/ui/canvas_history_recording_service.py`
  - additions/bond-update history command assembly 분리
  - composite/single/no-op push 기준과 history-enabled guard 분리
- `app/ui/canvas_mark_scene_service.py`
  - atom-anchored mark add / pointer-center / offset 계산 분리
  - mark registry cleanup과 scene remove lifecycle 분리
- `app/ui/canvas_arrow_build_service.py`
  - reaction/resonance/curved/dotted/inhibition/equilibrium arrow build 분리
  - arrow head path append와 arrow pen 조립 분리
- `app/ui/canvas_chemdraw_shortcut_service.py`
  - object/generic/atom/bond ChemDraw shortcut dispatch 분리
  - label/bond/fuse hotkey decision table와 hovered target routing 분리
- `app/ui/canvas_hit_testing_service.py`
  - scene item lookup / atom-bond nearest hit / bond id lookup 분리
  - spatial index cell size / rebuild / atom-bond grid query / segment distance 계산 분리
- `app/ui/canvas_ring_fill_scene_service.py`
  - ring polygon rebuild / 2D rotate / 3D rotate / scene item 생성 분리
  - list-backed ring과 free polygon ring의 update-match 규칙 분리
- `app/ui/canvas_scene_decoration_build_service.py`
  - TS bracket rect/path/item builder와 orbital item factory 분리
  - preview arrow / preview TS bracket scene 등록 경계 분리
  - radical/plus/minus mark item builder와 mark center helper 분리
  - arrow builder façade가 `CanvasArrowBuildService` composition delegate로 축소
- `app/ui/main_window_workbook_document_service.py`
  - workbook save/restore document session orchestration 분리
  - clear/rebuild/fallback sheet, active index clamp, workbook write 분리
- `app/ui/main_window_canvas_logic.py`
  - active canvas resolution / tab index / sheet index 계산 분리
  - canvas template-setting copy와 active canvas callback binding 분리
  - workbook sheet serialize / restorable sheet filtering / malformed content 정규화 분리
  - active sheet index coercion / clamp, default sheet-name counter seed 계산 분리
- `app/ui/main_window_active_canvas_ui_service.py`
  - active canvas callback bind / preview RDKit sync 분리
  - atom input / zoom label / tool sync / preview refresh orchestration 분리
  - canvas-tab changed의 plus-tab / invalid / non-canvas / canvas branch 분리
- `app/ui/main_window_canvas_tab_ui_service.py`
  - plus-tab invariant / delete guard / context-menu delete routing 분리
  - new-sheet creation과 tab-move correction orchestration 분리
- `app/ui/main_window_canvas_sheet_service.py`
  - canvas create / add-sheet / open-result-sheet orchestration 분리
  - active canvas template copy, plus-tab 앞 insert, name 생성 경계 분리
- `app/ui/main_window_text_style_service.py`
  - text color / align / note box / note border / text preset action 분리
  - `QColorDialog` 호출과 label-to-canvas preset mapping 분리
- `app/ui/main_window_tool_action_service.py`
  - checkable tool `QAction` 생성과 late-bound icon lookup 분리
  - bond tool / mark tool callback wiring과 tool action build 분리
- `app/ui/main_window_icon_factory.py`
  - toolbar icon painter / pixmap factory / benzene-chair geometry helper 분리
  - arrow preview / template preview / bond style icon painter 분리
- `app/ui/main_window_document_action_service.py`
  - save/load/export dialog + file action orchestration 분리
  - save/export/load failure warning과 status bar update 분리
  - bond-length dialog assembly와 confirm apply 경계 분리
- `app/ui/main_window_tool_routing_service.py`
  - template/arrow/palette menu wiring과 action callback dispatch 분리
  - color/ring-fill preset apply scheduling과 menu icon helper 분리
- `app/ui/main_window_tool_state_service.py`
  - tool/action checked-state sync와 status bar update 분리
  - bond/arrow/orbital preset mapping과 canvas setter dispatch 분리
- `app/ui/main_window_ui_assembly_service.py`
  - toolbar/button/menu widget assembly 분리
  - panel dock / theme apply / arrow settings dialog assembly 분리
  - `ArrowButton` / `CornerMenuButton` paint와 save-menu composition 경계 분리
- `app/ui/selection_highlight_styler.py`
  - selection highlight set/clear/apply pen mutation 분리
  - group child 재귀 적용과 original pen restore lifecycle 공통화
- `app/ui/handle_overlay_service.py`
  - handle clear/show/create overlay lifecycle 분리
  - `_active_handles` / `_handle_target` session reset 공통화
- `app/ui/handle_mutation_service.py`
  - orbital scale/rotate mutation 분리
  - curved control update와 selection outline refresh 분리
- `app/ui/curved_arrow_path_service.py`
  - curved arrow path rebuild와 arrow head append 공통화
  - `CanvasView._set_curved_arrow_path()`와 handle mutation이 같은 builder를 공유하도록 정리
- `app/ui/structure_benzene_logic.py`
  - benzene attach-bond / attach-atom / free fallback plan 분리
  - bond geometry failure terminal 처리와 free-center 차단 규칙 공통화
- `app/ui/structure_growth_logic.py`
  - fused benzene center 계산 분리
  - crown ether element stride, bond midpoint resolution, mirrored template point 변환 분리
  - alternating ring bond spec와 bond-result other-end resolution 공통화
- `app/ui/canvas_geometry_logic.py`
  - line/segment/ray/rect 교차 계산 분리
  - `CanvasGeometryController`의 순수 기하 계산 묶음을 별도 helper로 이동
- `app/ui/selection_center_logic.py`
  - atom-set centroid 계산 분리
  - atom-set bounding-box center 계산 분리
- `app/ui/selection_rotation_logic.py`
  - selected bond -> rotation atom set 확장 규칙 분리
  - 2D selection rotation 좌표 계산 분리
- `app/ui/main_window_toolbar_logic.py`
  - template entry callback 생성 분리
  - bond/arrow/orbital preset mapping 분리
  - toolbar checked-action sync key 계산 분리
  - tool display name mapping 분리
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
  - `CanvasView` wrapper가 직접 호출하는 public seam(`insert_session_state`, `begin_ring_template_insert`, preview/commit helpers)을 명시적으로 노출
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
  - `_add_mark_hover_preview()`가 mark hover preview service 경유로 축소
  - `_update_hover_highlight()`의 decision이 pure helper 경유로 축소
  - `clear_handles()` / `show_orbital_handles()` / `show_curved_handles()` / `_create_handle()`가 `HandleOverlayService` delegation wrapper로 축소
  - `_update_orbital_scale()` / `_update_orbital_rotate()` / `_update_curved_control()`가 `HandleMutationService` delegation wrapper로 축소
  - `_set_curved_arrow_path()`가 `CurvedArrowPathService` delegation wrapper로 축소
  - insert wrapper가 private helper 대신 `InsertController` public API로만 위임되도록 정리
  - selection wrapper / note-selection wrapper / selection geometry wrapper가 `SelectionController` public API로만 위임되도록 정리
  - `_selection_controller`에 test double/proxy를 직접 주입할 수 있게 seam을 완화
  - graph topology / adjacency / rotation-axis helper가 `CanvasGraphService` delegation wrapper로 축소
  - `add_atom()` / `_remove_atom_only()` / `_restore_atom_from_state()` / `apply_atom_color()`가 `CanvasAtomMutationService` delegation wrapper로 축소
  - `add_bond()` / `_restore_bond_from_state()` / `_remove_bond_by_id()` / `_trim_bonds_to_length()`가 `CanvasBondMutationService` delegation wrapper로 축소
  - `apply_color_to_item()` / `apply_ring_fill_color()`가 `CanvasColorMutationService` delegation wrapper로 축소
  - `_record_label_change()` / `_atom_item_for_id()` / `_ensure_carbon_dot()` / `_remove_carbon_dot()` / `_position_label()` / `_restore_atom_item_interaction()`가 `AtomLabelService` delegation wrapper로 축소
  - `_snapshot_state()` / `_restore_state()` / `restore_state()` / `save_to_file()` / `load_from_file()`가 `CanvasDocumentSessionService` delegation wrapper로 축소
  - `_record_additions()` / `_record_bond_update()`가 `CanvasHistoryRecordingService` delegation wrapper로 축소
  - `add_text_note()`가 `CanvasNoteController.create_text_note()` delegation wrapper로 축소
  - arrow / TS bracket / orbital build helper와 preview helper가 `CanvasSceneDecorationBuildService` delegation wrapper로 축소
  - `add_mark_for_atom()` / `_mark_offset_from_click()` / `_remove_mark_item()` / `_remove_marks_for_atom()` / `_mark_center_for_pointer()`가 `CanvasMarkSceneService` delegation wrapper로 축소
  - `_build_mark_item()` / `_mark_center()` / `_set_mark_center()`가 `CanvasSceneDecorationBuildService` delegation wrapper로 축소
  - `_update_ring_fills_for_atoms()` / `_rotate_ring_fills_3d()` / `_rotate_ring_fills()` / `_create_ring_fill_item()`가 `CanvasRingFillSceneService` delegation wrapper로 축소
  - `_handle_chemdraw_shortcut()` / `_handle_chemdraw_object_shortcut()` / `_handle_chemdraw_generic_hotkey()` / `_handle_chemdraw_atom_hotkey()` / `_handle_chemdraw_bond_hotkey()`가 `CanvasChemdrawShortcutService` delegation wrapper로 축소
  - `item_at_scene_pos()` / `find_atom_near()` / `_find_bond_near()` / `_nearest_atom_hit()` / `_nearest_bond_hit()` / `_ensure_spatial_index()` / `_rebuild_spatial_index()`가 `CanvasHitTestingService` delegation wrapper로 축소
  - `_sprout_regular_ring_from_atom()` / `_fuse_regular_ring_to_bond()` / `_fuse_chair_to_bond()`가 service delegation wrapper로 축소
  - `_sprout_bond_from_atom()` / `_sprout_benzene_from_atom()` / `_sprout_acetyl_from_atom()` / `_fuse_benzene_to_bond()`가 service delegation wrapper로 축소
  - `_sprout_bond_endpoint()` / `_regular_ring_points_for_atom()` / `_regular_ring_points_for_bond()` / `_template_points_for_bond()`가 pure helper adapter로 축소
  - `add_mark()` / `add_arrow()` / `add_ts_bracket()` / `add_orbital()`가 `SceneDecorationService` delegation wrapper로 축소
  - chair/boat, fused heterocycle, sidechain/functional fragment, `peptide_2` public builder가 `StructureBuildService` delegation wrapper로 축소
- `app/ui/canvas_handle_controller.py`
  - selection highlight pen mutation 제거
  - handle clear/show/create lifecycle 제거
  - orbital/curved mutation 제거
  - 현재 역할은 handle drag dispatch와 geometry wrapper 중심으로 축소
- `app/ui/canvas_geometry_controller.py`
  - line/segment/ray/rect 순수 계산 제거
  - `mark_target_distance_for_atom()`이 canvas wrapper 우회 없이 pure helper를 직접 사용하도록 정리
  - controller는 canvas state 기반 geometry orchestration과 adapter 역할 중심으로 축소
- `app/ui/selection_controller.py`
  - selection center marker용 bounding-box center 계산이 pure helper를 직접 사용하도록 정리
  - `CanvasView` wrapper가 호출하는 structure hit/item, note selection, selection outline/path/overlay helper를 public API로 정리
  - `_nearest_atom_hit()` / `_nearest_bond_hit()` 중복 계산이 `CanvasHitTestingService` consumer로 축소
- `app/ui/canvas_rotation_preview_controller.py`
  - selection preview의 selected bond -> atom 확장과 center 계산이 pure helper를 직접 사용하도록 정리
- `app/ui/selection_rotation_controller.py`
  - 3D rigid rotation path의 selected bond -> atom 확장과 bounding-box center 계산이 pure helper를 직접 사용하도록 정리
- `app/ui/main_window.py`
  - template entry, bond/arrow/orbital preset mapping, checked-action sync key 계산이 `main_window_toolbar_logic` 경유로 축소
  - active canvas resolve / callback bind / workbook save-restore 계산이 `main_window_canvas_logic` helper 경유로 축소
  - `_create_toolbar_button()` / `_create_corner_menu_button()` / `_create_save_menu_button()` / `_init_toolbars()` / `_init_panels()` / `_apply_theme()` / `_open_arrow_settings()`가 `MainWindowUIAssemblyService` delegation wrapper로 축소
  - `_normalize_xyz_export_path()` / `_default_xyz_export_path()` / `_default_save_dialog_path()` / `_save_canvas_to_path()` / `_save_canvas()` / `_save_canvas_as()` / `_export_xyz()` / `_load_canvas()` / `_set_bond_length()`가 `MainWindowDocumentActionService` delegation wrapper로 축소
  - `_add_menu_action()` / `_palette_icon()` / `_populate_template_menu()` / `_populate_arrow_menu()` / `_populate_palette_menu()` / `_activate_arrow_type_from_menu()` / `_activate_arrow_preset_from_menu()` / `_template_entries()` / `_acs_color_palette()` / `_apply_color_preset()` / `_apply_ring_fill_preset()`가 `MainWindowToolRoutingService` delegation wrapper로 축소
  - `_set_bond_style()` / `_sync_tool_actions_from_canvas()` / `_set_tool_with_status()` / `_set_arrow_type()` / `_set_orbital_type()` / `_set_orbital_phase()` / `_set_arrow_preset()`가 `MainWindowToolStateService` delegation wrapper로 축소
  - `_set_text_color()` / `_set_text_align()` / `_set_note_box_color()` / `_set_note_border_color()` / `_set_text_preset()`가 `MainWindowTextStyleService` delegation wrapper로 축소
  - `_make_icon()` / `_benzene_icon_polygon()` / `_benzene_icon_inner_segments()` / `_draw_arrow_head()` / `_chair_icon_rect()` / `_chair_icon_points()`와 각종 `_icon_*()` painter helper가 `MainWindowIconFactory` delegation wrapper로 축소
  - `_bind_active_canvas()` / `_handle_selection_info()` / `_current_zoom_percent()` / `_refresh_active_canvas_ui()` / `_on_canvas_tab_changed()`가 `MainWindowActiveCanvasUIService` delegation wrapper로 축소
  - `_ensure_add_sheet_tab()` / `_keep_add_tab_last()` / `_on_canvas_tab_moved()` / `_can_delete_canvas_sheet()` / `_show_canvas_tab_context_menu()` / `_delete_canvas_sheet()` / `_new_canvas_sheet()`가 `MainWindowCanvasTabUIService` delegation wrapper로 축소
  - `_create_canvas()` / `_add_canvas_sheet()` / `_open_result_canvas_sheet()`가 `MainWindowCanvasSheetService` delegation wrapper로 축소
  - `_clear_canvas_sheets()` / `_workbook_state()` / `_restore_single_sheet_document()` / `_restore_workbook_document()` / `_save_document_state()`가 `MainWindowWorkbookDocumentService` delegation wrapper로 축소
  - `_build_checkable_tool_action()` / `_activate_bond_style_tool()` / `_activate_mark_tool()` / `_build_tool_actions()`가 `MainWindowToolActionService` delegation wrapper로 축소
  - toolbar/panel/theme/dialog 조립, document/file action, menu routing, tool/state sync, active-canvas UI wiring, canvas-tab UI invariant, workbook document session, canvas-sheet/open-result orchestration은 service로 이동하고, `MainWindow`는 residual late-bound wiring 중심으로 축소
- `app/core/history.py`
  - scene-item history command가 공통 `scene_item_access` helper를 사용하도록 정리
  - create / restore / remove / apply / mark restore 경로를 controller-first access layer로 통일
  - `ChangeAtomLabelCommand`가 공통 `atom_label_access` helper를 사용하도록 정리
- `app/ui/canvas_note_controller.py`
  - note focus-out 삭제 경로가 공통 `scene_item_access` helper를 사용하도록 정리
  - `create_text_note()`가 note 생성/scene 등록/style 적용 orchestration을 흡수
  - note border disable fallback이 `QPen(Qt.PenStyle.NoPen)`을 쓰도록 수정해 `TypeError`를 제거
- `app/core/delete_tool_logic.py`
  - erase scene-item 삭제 경로가 공통 `scene_item_access` helper를 사용하도록 정리
- `app/ui/structure_insert_service.py`
  - inserted atom label apply가 `CanvasView` public wrapper 대신 공통 `atom_label_access`를 사용하도록 정리
- `app/ui/insert_commit_service.py`
  - smiles commit label apply가 `CanvasView` public wrapper 대신 공통 `atom_label_access`를 사용하도록 정리

### 2.3 새로 추가되거나 강화된 테스트

- `tests/test_atom_label_access.py`
- `tests/test_graphics_items.py`
- `tests/test_structure_build_service.py`
- `tests/test_structure_geometry_logic.py`
- `tests/test_ring_occupancy_logic.py`
- `tests/test_benzene_preview_service.py` 추가 보강
- `tests/test_bond_hover_preview_service.py`
- `tests/test_mark_hover_preview_service.py`
- `tests/test_hover_highlight_logic.py`
- `tests/test_hover_scene_service.py`
- `tests/test_hover_interaction_service.py` 추가 보강
- `tests/test_selection_highlight_styler.py`
- `tests/test_handle_overlay_service.py`
- `tests/test_handle_mutation_service.py`
- `tests/test_curved_arrow_path_service.py`
- `tests/test_structure_benzene_logic.py` 추가 보강
- `tests/test_structure_growth_logic.py`
- `tests/test_canvas_geometry_logic.py` 추가 보강
- `tests/test_selection_center_logic.py`
- `tests/test_selection_rotation_logic.py`
- `tests/test_canvas_geometry_controller.py`
- `tests/test_main_window_toolbar_logic.py`
- `tests/test_atom_label_service.py`
- `tests/test_canvas_atom_mutation_service.py` 추가 보강
- `tests/test_canvas_color_mutation_service.py`
- `tests/test_canvas_bond_mutation_service.py` 추가 보강
- `tests/test_canvas_document_session_service.py`
- `tests/test_canvas_history_recording_service.py` 추가 보강
- `tests/test_canvas_mark_scene_service.py`
- `tests/test_canvas_arrow_build_service.py`
- `tests/test_canvas_chemdraw_shortcut_service.py`
- `tests/test_canvas_hit_testing_service.py` 추가 보강
- `tests/test_canvas_ring_fill_scene_service.py`
- `tests/test_canvas_scene_decoration_build_service.py`
- `tests/test_main_window_workbook_document_service.py`
- `tests/test_main_window_document_action_service.py`
- `tests/test_main_window_active_canvas_ui_service.py`
- `tests/test_main_window_canvas_sheet_service.py`
- `tests/test_main_window_canvas_tab_ui_service.py`
- `tests/test_main_window_text_style_service.py`
- `tests/test_main_window_dialog_actions.py` 추가 보강
- `tests/test_main_window_icons.py` 추가 보강
- `tests/test_main_window_tool_action_service.py`
- `tests/test_main_window_tool_routing_service.py`
- `tests/test_main_window_tool_state_service.py`
- `tests/test_scene_decoration_build_service.py`
- `tests/test_scene_decoration_service.py`
- `tests/test_bond_graphics_logic.py` 추가 보강
- `tests/test_insert_smiles_transaction.py`
- `tests/test_template_insert_logic.py` 추가 보강
- `tests/test_insert_commit_service.py` 추가 보강
- `tests/test_structure_payload_logic.py` 추가 보강
- `tests/test_scene_item_state_unit.py` 추가 보강
- `tests/test_insert_controller.py` 추가 보강
- `tests/test_text_tool_logic.py`
- `tests/test_delete_tool_logic.py`
- `tests/test_core_rdkit_adapter.py` failure branch 추가 보강
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
- `tests/test_canvas_view_note_wrapper_contract.py` 추가 보강
- `tests/test_scene_item_access.py`
- `tests/test_canvas_document_state.py`
- `tests/test_tools_unit.py` 추가 보강
- `tests/test_structure_insert_service.py` 추가 보강
- `tests/test_canvas_graph_service.py` 추가 보강
- `tests/test_bond_style_logic.py` 추가 보강
- `tests/test_canvas_view_additional.py` 추가 보강
- `tests/test_canvas_view_mark_helpers.py` 추가 보강
- `tests/test_main_window_icons.py` direct factory coverage로 재정렬
- `tests/test_main_window_canvas_logic.py`
- `tests/test_main_window_workbook_tabs.py` 추가 보강
- `tests/test_main_window_canvas_tab_ui_service.py` 추가 보강
- `tests/test_main_window_toolbar_actions.py` 추가 보강

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
- `MarkHoverPreviewService`의 atom/free hover preview orchestration contract 고정
- `hover_highlight_logic`의 clear/no-op/atom/bond/free preview decision contract 고정
- `HoverSceneService`의 clear/add atom/add bond/add preview/no-op direct contract 고정
- `HoverInteractionService`의 mark/no-atoms/atom-hit/bond-hit/invalid/noop orchestration contract 고정
- `SelectionHighlightStyler`의 set/clear/apply group recursion/original-pen-restore contract 고정
- `HandleOverlayService`의 clear/show/create direct contract 고정
- `HandleMutationService`의 orbital scale/rotate fallback, curved control update contract 고정
- `CurvedArrowPathService`의 path rebuild / arrow head append direct contract 고정
- `structure_benzene_logic`의 bond 우선 / atom fallback / failed bond terminal / blocked free-center contract 고정
- `structure_benzene_logic`의 `None` bond / missing endpoint fallback과 failed atom geometry terminal contract 고정
- `structure_growth_logic`의 fused center / crown stride / mirrored template / bond midpoint / alternating bond spec contract 고정
- `graphics_items`의 no-select rect paint와 atom dot/label hit-bound contract 고정
- `canvas_geometry_logic`의 line/segment/ray/rect pure geometry contract 고정
- `canvas_geometry_logic`의 clip reject, `u1 > u2`, `t_min > t_max`, `t_max < 0` branch contract 고정
- `StructureBuildService.sprout/fuse ring-template helper`의 record/no-op contract 고정
- `StructureBuildService.sprout bond/benzene/acetyl + fuse benzene helper`의 direct contract 고정
- `StructureBuildService`의 chair/boat, fused heterocycle, sidechain/functional fragment, `peptide_2` builder contract 고정
- `structure_geometry_logic`의 sprout endpoint / ring attach / template projection / free benzene geometry contract 고정
- `CanvasView._add_bond_between_points()` / `add_benzene_ring()`가 service delegation shim으로 동작한다는 smoke 고정
- `CanvasView._benzene_ring_points()`가 service delegation shim으로 동작한다는 smoke 고정
- `CanvasView._ring_polygon_points_for_bond()`가 occupancy helper delegation shim으로 동작한다는 smoke 고정
- `CanvasView._clear_benzene_preview()` / `_render_benzene_preview()`가 preview service delegation shim으로 동작한다는 smoke 고정
- `CanvasView._add_bond_style_hover_preview()` / `_add_bond_tool_hover_preview()`가 hover preview service delegation shim으로 동작한다는 smoke 고정
- `CanvasView._add_mark_hover_preview()`가 mark hover preview service delegation shim으로 동작한다는 smoke 고정
- `_update_hover_highlight()`의 state decision이 pure helper contract를 따르도록 고정
- `BondHoverPreviewService` / `MarkHoverPreviewService`가 hover scene service-first 경로를 우선 사용한다는 smoke 고정
- `CanvasView._clear_hover_highlight()` / `_add_atom_hover_indicator()` / `_add_bond_hover_indicator()` / `_add_hover_preview_items()`가 hover scene service delegation shim으로 동작한다는 smoke 고정
- `CanvasView._update_hover_highlight()`가 hover interaction service delegation shim으로 동작한다는 smoke 고정
- `CanvasView._set_selection_highlight()` / `_clear_selection_highlight()` / `_apply_selection_style()`가 selection highlight styler delegation shim으로 동작한다는 smoke 고정
- `CanvasView` selection wrapper가 injected controller seam을 통해 public API로 위임된다는 contract 고정
- `CanvasView.begin_ring_template_insert()`를 포함한 insert wrapper가 `InsertController` public API로 위임된다는 contract 고정
- `CanvasView` graph/topology wrapper가 `CanvasGraphService` public API로 위임된다는 contract 고정
- `CanvasGraphService`의 duplicate-bond adjacency guard, cycle cache invalidation, rotation-hint rejection contract 고정
- `CanvasGraphService`의 partial-selection dead fallback 제거와 rotation side/axis boundary, isolated/no-rotatable selection fallback contract 고정
- `CanvasView.add_atom()` / `_remove_atom_only()` / `_restore_atom_from_state()` / `apply_atom_color()`가 `CanvasAtomMutationService` public API로 위임된다는 contract 고정
- `CanvasAtomMutationService`의 atom add/remove/restore/color lifecycle contract 고정
- `CanvasView.add_bond()` / `_restore_bond_from_state()` / `_remove_bond_by_id()` / `_trim_bonds_to_length()`가 `CanvasBondMutationService` public API로 위임된다는 contract 고정
- `CanvasBondMutationService`의 duplicate-bond no-op, sparse restore, adjacency rewire, trim cleanup contract 고정
- `CanvasBondMutationService`의 `None` bond remove, empty-state restore, service resolver fallback contract 고정
- `CanvasView.apply_color_to_item()` / `apply_ring_fill_color()`가 `CanvasColorMutationService` public API로 위임된다는 contract 고정
- `CanvasColorMutationService`의 bond/atom/ring recolor와 ring-fill history contract 고정
- `AtomLabelService`의 carbon-dot lifecycle, label positioning, selected replacement restore, label-change history assembly contract 고정
- `CanvasView._record_label_change()` / `_atom_item_for_id()` / `_ensure_carbon_dot()` / `_remove_carbon_dot()` / `_position_label()` / `_restore_atom_item_interaction()`가 `AtomLabelService` public API로 위임된다는 contract 고정
- `CanvasDocumentSessionService`의 restore 순서, history disable/reenable, save/load/history-reset contract 고정
- `CanvasView._snapshot_state()` / `_restore_state()` / `restore_state()` / `save_to_file()` / `load_from_file()`가 `CanvasDocumentSessionService` public API로 위임된다는 contract 고정
- `CanvasHistoryRecordingService`의 composite/single/no-op additions push와 bond-update history guard contract 고정
- `CanvasHistoryRecordingService`의 empty sparse atom range, `None` new bond, `None`-only scene item no-op contract 고정
- `CanvasView._record_additions()` / `_record_bond_update()`가 `CanvasHistoryRecordingService` public API로 위임된다는 contract 고정
- `CanvasNoteController.create_text_note()`의 note item 생성/registry/style contract 고정
- `CanvasView.add_text_note()`가 `CanvasNoteController` public API로 위임된다는 contract 고정
- `CanvasView.clear_handles()` / `show_orbital_handles()` / `show_curved_handles()` / `_create_handle()`가 handle overlay service delegation shim으로 동작한다는 smoke 고정
- `CanvasView._update_orbital_scale()` / `_update_orbital_rotate()` / `_update_curved_control()`가 handle mutation service delegation shim으로 동작한다는 smoke 고정
- `CanvasView._set_curved_arrow_path()`가 curved arrow path service delegation shim으로 동작한다는 smoke 고정
- `StructureBuildService.benzene_ring_points()`가 pure benzene plan helper를 경유하면서 기존 bond/atom/free fallback contract를 유지한다는 direct test 고정
- `CanvasGeometryController`의 line/segment/ray/rect helper가 pure geometry module과 wrapper delegation 계약을 유지한다는 direct/wrapper test 고정
- `CanvasView._sprout_regular_ring_from_atom()` / `_fuse_regular_ring_to_bond()` / `_fuse_chair_to_bond()`가 service delegation shim으로 동작한다는 smoke 고정
- `CanvasView._sprout_bond_from_atom()` / `_sprout_benzene_from_atom()` / `_sprout_acetyl_from_atom()` / `_fuse_benzene_to_bond()`가 service delegation shim으로 동작한다는 smoke 고정
- `CanvasView` geometry helper wrapper가 pure helper 결과를 `QPointF`/merge로 adapter한다는 smoke 고정
- `SceneDecorationService.add_mark()` / `add_arrow()` / `add_ts_bracket()` / `add_orbital()` contract 고정
- `CanvasView.add_mark()` / `add_arrow()` / `add_ts_bracket()` / `add_orbital()`가 service delegation shim으로 동작한다는 smoke 고정
- `CanvasSceneDecorationBuildService`의 arrow dispatch / curved metadata / TS bracket builder / orbital item factory / preview scene registration contract 고정
- `CanvasArrowBuildService`의 arrow dispatch / curved metadata / preview add / pen contract 고정
- `bond_graphics_logic`의 non-selectable original/replacement item fallback과 selection restore contract 고정
- `template_insert_logic`의 invalid internal bond plan, unknown generator, missing template shape guard contract 고정
- `BenzenePreviewService._create_inner_bond_item()`의 secondary item missing fallback contract 고정
- `CanvasSceneDecorationBuildService`의 mark builder / mark center helper contract 고정
- `CanvasSceneDecorationBuildService`의 arrow façade가 `CanvasArrowBuildService`로 위임된다는 contract 고정
- `CanvasMarkSceneService`의 mark add / offset / cleanup / pointer-center contract 고정
- `CanvasView` arrow / TS bracket / orbital build wrapper가 `CanvasSceneDecorationBuildService` public API로 위임된다는 contract 고정
- `CanvasView` mark scene wrapper가 `CanvasMarkSceneService` public API로 위임된다는 contract 고정
- `CanvasRingFillSceneService`의 ring rebuild / 2D rotate / 3D rotate / item creation contract 고정
- `CanvasView` ring fill wrapper가 `CanvasRingFillSceneService` public API로 위임된다는 contract 고정
- `CanvasChemdrawShortcutService`의 object/generic/atom/bond hotkey dispatch contract 고정
- `CanvasView` ChemDraw shortcut wrapper가 `CanvasChemdrawShortcutService` public API로 위임된다는 contract 고정
- `CanvasHitTestingService`의 scene lookup / spatial index / nearest hit / bond-id direct contract 고정
- `CanvasHitTestingService`의 empty bond graphic fallback, zero-cell guard, sparse atom/bond grid tolerance contract 고정
- `CanvasView` hit-testing wrapper가 `CanvasHitTestingService` public API로 위임된다는 contract 고정
- `SelectionController` nearest-hit helper가 `CanvasHitTestingService` consumer로 동작한다는 contract 고정
- `CanvasView`의 chair/boat, fused heterocycle, sidechain/functional fragment, `peptide_2` public builder가 `StructureBuildService` delegation shim으로 동작한다는 smoke 고정
- `MainWindow` workbook restore가 invalid/non-canvas sheet를 건너뛰고 active sheet index를 coercion/clamp하며 malformed content를 방어하고 empty workbook에 fallback sheet를 만든다는 contract 고정
- workbook restore 이후 default sheet name counter가 resync돼 새 canvas tab이 기존 이름을 재사용하지 않는다는 contract 고정
- `MainWindow._delete_canvas_sheet()`가 plus tab / last remaining canvas guard를 지킨다는 workbook tab contract 고정
- `MainWindow` document/file wrapper가 `MainWindowDocumentActionService` public API로 위임된다는 contract 고정
- `MainWindowDocumentActionService`의 save/load/export/bond-length dialog contract 고정
- `MainWindow` canvas-tab wrapper가 `MainWindowCanvasTabUIService` public API로 위임된다는 contract 고정
- `MainWindowCanvasTabUIService`의 plus-tab invariant, delete guard, context-menu delete routing contract 고정
- `MainWindowCanvasSheetService`의 canvas create / add-sheet / open-result-sheet / new-sheet contract 고정
- `MainWindow` canvas-sheet wrapper가 `MainWindowCanvasSheetService` public API로 위임된다는 contract 고정
- `MainWindowTextStyleService`의 color dialog / align mapping / text preset dispatch contract 고정
- `MainWindow` text style wrapper가 `MainWindowTextStyleService` public API로 위임된다는 contract 고정
- `MainWindowIconFactory`의 benzene/chair geometry와 icon painter contract 고정
- `MainWindow` icon helper wrapper가 `MainWindowIconFactory` public API와 late-bound string lookup을 유지한다는 contract 고정
- `MainWindow` menu/preset wrapper가 `MainWindowToolRoutingService` public API로 위임된다는 contract 고정
- `MainWindowToolRoutingService`의 template/arrow/palette menu wiring과 color/ring-fill preset apply contract 고정
- `MainWindowToolActionService`의 checkable action build, bond-style tool dispatch, mark tool dispatch contract 고정
- `MainWindow` tool action wrapper가 `MainWindowToolActionService` public API로 위임된다는 contract 고정
- `MainWindow` tool/state wrapper가 `MainWindowToolStateService` public API로 위임된다는 contract 고정
- `MainWindowToolStateService`의 checked-action sync, status bar update, bond/arrow/orbital setter dispatch contract 고정
- `MainWindowActiveCanvasUIService`의 callback rebinding, zoom rounding/clamp, atom-input/preview refresh, plus-tab/invalid tab branch contract 고정
- `MainWindow` active-canvas UI wrapper가 `MainWindowActiveCanvasUIService` public API로 위임된다는 contract 고정
- `MainWindowWorkbookDocumentService`의 clear/rebuild/fallback sheet, active index clamp, single-vs-workbook save contract 고정
- `MainWindow` workbook document wrapper가 `MainWindowWorkbookDocumentService` public API로 위임된다는 contract 고정
- `MainWindow` toolbar/panel/theme/dialog wrapper가 `MainWindowUIAssemblyService` public API로 위임된다는 contract 고정
- `MainWindowUIAssemblyService`의 button/menu assembly, toolbar/panel wiring, arrow-settings dialog contract 고정

## 3. 현재 우선 점검 대상

| 영역 | 규모 / 커버리지 | 근거 | 판단 |
| --- | --- | --- | --- |
| `app/ui/canvas_view.py` | `2224 stmts / 99%` | selection-copy/translation wrapper, projection anchor/center fallback, planar fragment invalid/collinear path, average-bond-length / rotation-scale guard까지 direct test로 메워 사실상 유지 단계다 | 급하지 않음 |
| `app/ui/preview_scene_renderer.py` | `107 stmts / 95%` | preview item rebuild/clear contract는 안정화됐고 남은 건 소수 paint/pen fallback branch다 | 다음 우선순위 |
| `app/ui/scene_clipboard_logic.py` | `102 stmts / 95%` | payload serialize/decode 경계는 안정화됐고 남은 건 compatibility/no-op tail이다 | 다음 우선순위 |
| `app/ui/scene_delete_logic.py` | `91 stmts / 95%` | delete plan helper는 정리됐고 남은 건 rare selection bucket branch다 | 다음 우선순위 |
| `app/ui/canvas_move_controller.py` | `125 stmts / 95%` | move controller는 wrapper/helper 구조가 정리돼 남은 건 drag guard와 release edge branch 수준이다 | 다음 우선순위 |
| `app/core/text_tool_logic.py` | `65 stmts / 95%` | target/prompt planning은 분리됐고 남은 건 소수 invalid/default branch다 | 다음 우선순위 |
| `app/ui/selection_controller.py` | `465 stmts / 97%` | public wrapper, object/bond path helper, overlay/no-op arc, invalid target selection path까지 direct test로 정리돼 사실상 마무리 단계다 | 급하지 않음 |
| `app/ui/bond_renderer.py` | `697 stmts / 99%` | 3D/2D ring double style variant, dotted-double ring-center path, bold/plain-double update/add matrix를 direct test로 메워 사실상 마무리 단계다 | 급하지 않음 |
| `app/ui/preview_3d.py` | `232 stmts / 99%` | rebuild guard, mouse/wheel input, `_safe_update()`, empty projection paint path까지 닫혀 유지 단계로 들어갔다 | 급하지 않음 |
| `app/ui/canvas_arrow_build_service.py` | `100%` | arrow matrix direct test를 보강해 specialized arrow와 double-head helper branch까지 닫았다 | 급하지 않음 |
| `app/ui/canvas_hit_testing_service.py` | `100%` | empty bond graphic fallback, zero-cell guard, sparse grid tolerance까지 닫혀 유지 단계다 | 급하지 않음 |
| `app/ui/canvas_chemdraw_shortcut_service.py` | `100%` | object/generic/atom/bond shortcut matrix와 service resolver까지 direct test로 닫혀 유지 단계다 | 급하지 않음 |
| `app/ui/canvas_scene_decoration_build_service.py` | `100%` | orbital matrix와 orbital geometry branch까지 direct test로 닫혀 유지 단계로 들어갔다 | 급하지 않음 |
| `app/ui/canvas_scene_reset_service.py` | `100%` | `CanvasView.clear_scene()` reset lifecycle과 factory seam이 별도 경계로 분리되어 direct/wrapper contract까지 고정됐다 | 급하지 않음 |
| `app/ui/canvas_ring_fill_scene_service.py` | `126 stmts / 99%` | list-backed/non-list ring update와 2D/3D rotate branch가 거의 닫혀 소수 compatibility tail만 남았다 | 급하지 않음 |
| `app/ui/canvas_mark_scene_service.py` | `100%` | missing-atom/no-registry/remove fallback과 service resolver까지 direct test로 닫혀 유지 단계다 | 급하지 않음 |
| `app/ui/canvas_document_session_service.py` | `100%` | document session 경계는 direct/wrapper test까지 들어가 안정화됐다 | 급하지 않음 |
| `app/ui/canvas_history_recording_service.py` | `100%` | additions/bond-update command assembly와 sparse/no-op path까지 닫혀 유지 단계다 | 급하지 않음 |
| `app/ui/canvas_note_controller.py` | `107 stmts / 99%` | note lifecycle은 생성/삭제/style/box fallback까지 정리됐고 border-disable `TypeError`도 제거돼 사실상 마무리 단계다 | 급하지 않음 |
| `app/ui/atom_label_service.py` | `224 stmts / 96%` | 이번에 helper/history 경계를 흡수했고 direct contract도 고정돼 안정권에 들어갔다 | 급하지 않음 |
| `app/ui/canvas_color_mutation_service.py` | `100 stmts / 99%` | invalid/no-op/factory seam까지 direct test로 메워 사실상 유지 단계다 | 급하지 않음 |
| `app/ui/canvas_atom_mutation_service.py` | `100%` | sparse neighbor/bond index, empty-state restore, factory resolver까지 direct test로 닫혀 유지 단계다 | 급하지 않음 |
| `app/ui/canvas_bond_mutation_service.py` | `100%` | `None` bond remove, empty-state restore, resolver fallback까지 direct test로 닫혀 유지 단계다 | 급하지 않음 |
| `app/ui/canvas_graph_service.py` | `100%` | cycle/rotation-axis/factory seam과 boundary/isolated fallback까지 direct test로 닫았고 dead duplicate fallback도 제거했다 | 급하지 않음 |
| `app/ui/canvas_input_controller.py` | `100%` | key press routing, shortcut override, native gesture, copy/paste false fallthrough까지 direct test로 닫고 dead delete tail도 제거했다 | 급하지 않음 |
| `app/ui/canvas_handle_controller.py` | `100%` | overlay/mutation/highlight delegation, handle drag dispatch, snap-distance wrapper까지 direct test로 닫혀 유지 단계다 | 급하지 않음 |
| `app/ui/benzene_preview_renderer.py` | `100%` | detached/disposed clear path, empty ring, inner-none, preview-style helper branch까지 direct test로 닫혔다 | 급하지 않음 |
| `app/core/tools.py` | `828 stmts / 99%` | base/select/bond/move/delete/benzene/color/flip/edit/perspective guard와 no-op arc를 direct test로 메워 사실상 마무리됐다 | 급하지 않음 |
| `app/ui/scene_item_controller.py` | `133 stmts / 99%` | `attach_scene_item()` seam으로 runtime add와 restore를 같은 registry 규칙으로 묶었고 남은 건 미세 branch arc 수준이다 | 급하지 않음 |
| `app/core/document_state.py` | `100%` | wrapped/bare payload guard, non-mapping/list tolerance, internal default mapping fallback까지 direct test로 닫혀 유지 단계다 | 급하지 않음 |
| `app/ui/canvas_document_state.py` | `100%` | snapshot attached/disposed filter, empty arrow skip, settings apply fallback까지 direct test로 닫혀 유지 단계다 | 급하지 않음 |
| `app/ui/structure_build_service.py` | `100%` | builder edge/no-op/fallback까지 direct test로 닫혀 유지 단계로 들어갔다 | 급하지 않음 |
| `app/ui/canvas_geometry_controller.py` | `100%` | ring lookup / label padding helper와 stateful branch direct test를 마쳐 유지 단계로 들어갔다 | 급하지 않음 |
| `app/ui/structure_geometry_logic.py` | `100%` | geometry lookup/result packaging helper와 invalid/default direct test까지 닫혀 유지 단계로 들어갔다 | 급하지 않음 |
| `app/ui/main_window.py` | `100%` | active-canvas no-op/error, result-sheet naming, panel/zoom helper, 잔여 icon wrapper까지 direct test로 닫혀 유지 단계다 | 급하지 않음 |
| `app/ui/main_window_tool_action_service.py` | `100%` | tool action build와 callback wiring은 direct/wrapper test까지 들어가 안정화됐다 | 급하지 않음 |
| `app/ui/main_window_icon_factory.py` | `100%` | painter matrix direct test를 보강했고 dead guard branch도 정리해 유지 단계로 들어갔다 | 급하지 않음 |
| `app/ui/main_window_canvas_sheet_service.py` | `100%` | canvas-sheet/open-result create 경계는 direct test까지 들어가 안정화됐다 | 급하지 않음 |
| `app/ui/main_window_text_style_service.py` | `100%` | color dialog / setter dispatch helper와 no-op branch direct test까지 들어가 유지 단계다 | 급하지 않음 |
| `app/ui/main_window_active_canvas_ui_service.py` | `100%` | active-canvas bind/refresh/change 경계는 direct/wrapper test까지 들어가 안정화됐다 | 급하지 않음 |
| `app/ui/main_window_workbook_document_service.py` | `100%` | workbook save/restore document session 경계는 direct/wrapper test까지 들어가 안정화됐다 | 급하지 않음 |
| `app/ui/main_window_canvas_tab_ui_service.py` | `100%` | tab guard/reselect/new-sheet contract를 direct test로 메웠고 unreachable delete guard도 정리했다 | 급하지 않음 |
| `app/ui/main_window_document_action_service.py` | `116 stmts / 99%` | save/load/export/bond-length 경계는 새 service로 안정화됐고 contract test도 충분하다 | 급하지 않음 |
| `app/ui/main_window_tool_routing_service.py` | `58 stmts / 99%` | menu wiring 경계는 새 service로 안정화됐고 남은 일은 사실상 없다 | 급하지 않음 |
| `app/ui/main_window_tool_state_service.py` | `100%` | tool/state sync 2차 routing은 direct/wrapper test까지 들어가 안정화됐다 | 급하지 않음 |
| `app/ui/main_window_ui_assembly_service.py` | `231 stmts / 99%` | toolbar/panel/theme/dialog assembly에 더해 `ArrowButton`/`CornerMenuButton` paint와 icon-only factory path까지 닫혀 유지 단계다 | 급하지 않음 |
| `app/ui/main_window_canvas_logic.py` | `82 stmts / 96%` | active canvas/workbook helper는 별도 경계로 안정화됐고 남은 건 malformed input 세부 branch 정도다 | 급하지 않음 |
| `app/ui/graphics_items.py` | `100%` | no-select rect paint, atom dot/label hit padding/radius fallback까지 direct test로 닫혀 유지 단계다 | 급하지 않음 |
| `app/ui/structure_benzene_logic.py` | `100%` | bond/atom/free precedence와 invalid attachment fallback까지 direct test로 닫혀 유지 단계다 | 급하지 않음 |
| `app/ui/bond_graphics_logic.py` | `100%` | selection restore와 non-selectable item fallback까지 direct test로 닫혀 유지 단계다 | 급하지 않음 |
| `app/ui/template_insert_logic.py` | `100%` | benzene special-case, internal invalid plan guard, missing template shape까지 direct test로 닫혀 유지 단계다 | 급하지 않음 |
| `app/ui/benzene_preview_service.py` | `100%` | preview clear/render와 inner-bond secondary item fallback까지 direct test로 닫혀 유지 단계다 | 급하지 않음 |
| `app/core/rdkit_conversion.py` | `464 stmts / 99%` | alias fragment failure matrix와 conformer/stereo swallow branch까지 거의 닫혀 남은 miss가 소수 비핵심 arc로 줄었다 | 급하지 않음 |
| `app/ui/scene_transform_logic.py` | `184 stmts / 99%` | transform helper는 사실상 안정화됐고 남은 miss는 note vertical valid-rect 정도다 | 급하지 않음 |
| `app/ui/scene_ops_controller.py` | `187 stmts / 98%` | orchestration controller로 거의 정리됐고 남은 리팩토링 ROI가 낮다 | 급하지 않음 |
| `app/ui/insert_controller.py` | `100%` | public wrapper seam과 smiles/template failure/clear preview tail까지 direct test로 닫혀 유지 단계다 | 급하지 않음 |

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
- `CanvasView._add_mark_hover_preview()`가 `MarkHoverPreviewService` 경유
- `CanvasView._update_hover_highlight()`의 clear/no-op/preview decision이 `hover_highlight_logic` 경유
- `CanvasView._clear_hover_highlight()` / `_add_atom_hover_indicator()` / `_add_bond_hover_indicator()` / `_add_hover_preview_items()`가 `HoverSceneService` 경유
- `CanvasView._update_hover_highlight()` apply/orchestration이 `HoverInteractionService` 경유
- `CanvasView._set_selection_highlight()` / `_clear_selection_highlight()` / `_apply_selection_style()`가 `SelectionHighlightStyler` 경유
- `CanvasView._structure_hit_from_item()` / `select_structure_for_item()` / note selection helper / selection geometry helper가 `SelectionController` public API 경유
- `CanvasView._insert_session_state()` / `begin_ring_template_insert()` / smiles/template preview/commit helper가 `InsertController` public API 경유
- `CanvasView` graph topology / adjacency / rotation-axis helper가 `CanvasGraphService` 경유
- `_selection_controller` seam이 injected test double/proxy를 직접 수용하도록 정리
- `CanvasView.clear_handles()` / `show_orbital_handles()` / `show_curved_handles()` / `_create_handle()`가 `HandleOverlayService` 경유
- `CanvasView._update_orbital_scale()` / `_update_orbital_rotate()` / `_update_curved_control()`가 `HandleMutationService` 경유
- `CanvasView._set_curved_arrow_path()`가 `CurvedArrowPathService` 경유
- `CanvasView.preview_arrow()` / `_build_arrow_item()` / `preview_ts_bracket()` / `_build_orbital_items()`가 `CanvasSceneDecorationBuildService` 경유
- `StructureBuildService.benzene_ring_points()`가 `structure_benzene_logic` 경유
- fused/crown/fuse 계산 일부가 `structure_growth_logic` 경유
- `MainWindow._create_canvas()` / `_add_canvas_sheet()` / `_open_result_canvas_sheet()`가 `MainWindowCanvasSheetService` 경유
- `MainWindowCanvasTabUIService.new_canvas_sheet()`가 `MainWindowCanvasSheetService`를 경유하도록 정리

이번 라운드로 `CanvasView`의 arrow / TS bracket / orbital build helper는 `CanvasSceneDecorationBuildService`로 넘어갔다. 남은 `CanvasView` 축소는 더 이상 builder 묶음이 아니라, scene add/restore adapter와 residual GUI edge branch 같은 add/scene orchestration 표면을 줄이는 쪽이 중심이다.

### 4.5 `MainWindow`는 canvas-sheet/open-result orchestration까지 끝났고, `RDKitConversion`은 targeted test 보강이 먼저 닫혔다

- `MainWindow`: toolbar/menu pure mapping, active-canvas/workbook 계산, active-canvas UI wiring, canvas-tab UI invariant, workbook document session, theme/widget assembly, document/file action, menu wiring, tool/state sync, canvas create/add/open-result orchestration까지 각각 `main_window_toolbar_logic`, `main_window_canvas_logic`, `MainWindowActiveCanvasUIService`, `MainWindowCanvasTabUIService`, `MainWindowWorkbookDocumentService`, `MainWindowUIAssemblyService`, `MainWindowDocumentActionService`, `MainWindowToolRoutingService`, `MainWindowToolStateService`, `MainWindowCanvasSheetService`로 분리 완료, 남은 건 residual late-bound UI branch
- `RDKitConversion`: strict label / unsupported stereobond / sanitize / 3D scene fallback 같은 user-visible failure branch는 보강 완료

둘 다 남은 일이 없지는 않지만, 현재 구조 리스크 대비 우선순위는 `CanvasSceneDecorationBuildService`의 branch matrix 보강, `CanvasView`의 ring fill scene lifecycle 정리, `MainWindow`의 icon/painter를 포함한 residual late-bound UI branch 정리 쪽이 먼저다.

## 5. 테스트 커버리지 확장 권장안

### 5.1 가장 먼저 늘릴 테스트

#### `SceneOpsController`

- clipboard payload mismatch 세부 변종
- orchestration smoke와 selection restore 정도만 유지하면 충분하다

#### `CanvasView`

- scene decoration build/orbital helper의 branch matrix 보강
- ring fill scene lifecycle 분리
- residual scene add/restore adapter smoke
- structure insert 후 selection 복원
- structure insert 시 title note 생성
- atom merge 후 duplicate bond 정리 우선순위
- `_redraw_bond()` caller 경유 selection 유지 smoke

#### `scene_transform_logic`

- note vertical valid-rect path

#### `core/tools.py`

- drag erase 누적 command 같은 드문 GUI 예외 경로
- 일부 미사용 base/default path 정도만 유지 보강

#### `MainWindow`

- icon/painter helper 분리
- residual late-bound UI wiring branch
- dialog/status/message update edge case

### 5.2 그 다음으로 늘릴 테스트

#### `SceneItemController`

- rare fallback arc 정도만 유지
- ring 관련 geometry refresh 호출 누락 방지

#### `RDKitConversionHelper`

- alias fragment failure matrix
- swallowed-exception branch
- multi-component layout edge case

## 6. 유지하는 편이 좋은 영역

아래 영역은 현재 구조와 테스트 균형이 좋다. 계속 기준점으로 삼기 좋다.

- `app/core/history.py`
- `app/core/template_geometry.py`
- `app/core/document_io.py`
- `app/core/rdkit_adapter.py`
- `app/ui/graphics_items.py`
- `app/ui/benzene_preview_service.py`
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
- `app/ui/structure_benzene_logic.py`

공통점:

- 책임 경계가 선명하다.
- 순수 로직 또는 얇은 service 형태다.
- 테스트 계약이 이미 비교적 단단하다.

## 7. 권장 실행 순서

1. `preview_scene_renderer`, `scene_clipboard_logic`, `scene_delete_logic`, `canvas_move_controller`, `text_tool_logic`의 95% edge branch를 먼저 줄인다.
2. `main_window_canvas_logic`, `handle_interaction_logic`, `hover_scene_renderer`, `main.py`, `perspective_drag_logic`, `tool_overlay_logic`의 96% branch를 메운다.
3. `selection_controller`, `selection_rotation_controller`, `atom_label_service`, `template_geometry`, `core/history`, `rdkit_conversion`의 97%대 유지성 polish를 진행한다.
4. 마지막으로 `CanvasView`, `bond_renderer`, `bond_preview_renderer`, `core/tools.py` 같은 99% arc는 ROI가 있을 때만 정리한다.

## 8. 결론

첫 보고서에서 제시한 방향은 여전히 맞다. 이번 라운드까지 오면서 `graphics_items`, `structure_benzene_logic`, `bond_graphics_logic`, `template_insert_logic`, `benzene_preview_service`도 `100%`까지 닫혔고, 전체 커버리지는 `99%`를 유지한 채 `1196 passed`까지 올라왔다. 이미 `InsertCommitService`, `SceneItemState`, `HoverInteractionService`, `MainWindow`, `CanvasInputController`, `CanvasHandleController`, `BenzenePreviewRenderer`, `core.document_state`, `canvas_document_state`, `CanvasMarkSceneService`, `CanvasChemdrawShortcutService`, `InsertController`, `MainWindowTextStyleService`, `CanvasGeometryController`, `StructureGeometryLogic`, `StructureBuildService`, `CanvasAtomMutationService`, `BondStyleLogic`, `StructureInsertService`, `CanvasGraphService`, `CanvasHistoryRecordingService`, `CanvasHitTestingService`, `CanvasBondMutationService`, `canvas_geometry_logic`가 `100%`이고, `CanvasNoteController`, `StructurePayloadLogic`, `CanvasRingFillSceneService`, `BondPreviewRenderer`, `BondRenderer`, `RDKitConversion`, `preview_3d`, `core/tools.py`, `main_window_ui_assembly_service`, `CanvasView`도 `99%`까지 올라와 있다. 현재 단계의 다음 초점은 큰 구조 추출보다 `preview_scene_renderer`, `scene_clipboard_logic`, `scene_delete_logic`, `canvas_move_controller`, `text_tool_logic` 같은 95%대 tail을 줄이는 것이다.

현재 총평:

- 방금 큰 구조 추출이 끝난 곳: `InsertController`, `core/tools.py` 1차 정리
- 이번에 닫은 항목: `CanvasView` graph/topology + rotation-axis helper의 `CanvasGraphService` 추출, `CanvasView` bond lifecycle의 `CanvasBondMutationService` 추출, `CanvasView` atom lifecycle의 `CanvasAtomMutationService` 추출, `CanvasView` color/ring-fill mutation의 `CanvasColorMutationService` 추출, `CanvasView` label/dot helper + label-change history assembler의 `AtomLabelService` 확장, `CanvasView` document session orchestration의 `CanvasDocumentSessionService` 추출, `CanvasView` history command assembly의 `CanvasHistoryRecordingService` 추출, `CanvasView` note creation seam의 `CanvasNoteController` 흡수, `CanvasView` scene decoration build/orbital helper의 `CanvasSceneDecorationBuildService` 추출, 그 안의 arrow build 묶음을 `CanvasArrowBuildService`로 재분리, `CanvasView` mark scene lifecycle의 `CanvasMarkSceneService` 추출, `CanvasView` ring fill scene lifecycle의 `CanvasRingFillSceneService` 추출, `CanvasView` ChemDraw shortcut seam의 `CanvasChemdrawShortcutService` 추출, `CanvasView` insert/selection wrapper seam, `MainWindow` active-canvas/workbook helper 추출, `MainWindowActiveCanvasUIService`를 통한 bind/refresh/change 분리, `MainWindowCanvasTabUIService`를 통한 plus-tab/delete/new-sheet invariant 분리, `MainWindowWorkbookDocumentService`를 통한 workbook save/restore document session 분리, `MainWindowCanvasSheetService`를 통한 canvas create/add/open-result orchestration 분리, `MainWindowTextStyleService`를 통한 text/note style action 분리, `MainWindowToolActionService`를 통한 tool action build/wiring 분리, `MainWindowIconFactory`를 통한 icon/painter helper 분리, `MainWindowUIAssemblyService`를 통한 toolbar/panel/theme/dialog assembly 분리, `MainWindowDocumentActionService`를 통한 save/load/export/bond-length action 분리, `MainWindowToolRoutingService`를 통한 template/arrow/palette menu wiring 분리, `MainWindowToolStateService`를 통한 tool/state sync 2차 routing 분리, workbook malformed restore 방어와 sheet-name counter resync, preview tool GUI smoke, `SceneOpsController` delete plan 분리, delete apply 분리, clipboard payload 분리, clipboard transaction 2차 분리, transform grouping/atom map 분리, transform apply/command assembly 분리, paste apply 분리, 단건 mutation helper 분리, bond redraw/selection restore 공통화, flip scene-item bounds/center/state helper 분리, `SceneDecorationService`를 통한 scene-decoration add/history 분리
- 이번에 닫은 항목에 추가: `CanvasView` / `SelectionController` hit-testing / spatial lookup 묶음의 `CanvasHitTestingService` 추출
- 이번에 닫은 항목에 추가: `CanvasArrowBuildService` branch matrix direct test 보강, `MainWindowIconFactory` painter matrix direct test 보강, painter dead guard cleanup
- 이번에 닫은 항목에 추가: `CanvasColorMutationService` invalid/no-op/factory seam direct test 보강, `CanvasGraphService` cycle/rotation-axis/factory seam direct test 보강, `CanvasSceneDecorationBuildService` orbital matrix/factory seam direct test 보강, `MainWindowCanvasTabUIService` tab guard/reselect direct test 보강
- 이번에 닫은 항목에 추가: `CanvasGraphService` dead `atoms_for_axis` guard 정리, `MainWindowCanvasTabUIService` unreachable `widget is not None` guard 정리
- 이번에 닫은 항목에 추가: `CanvasSceneDecorationBuildService` orbital geometry branch direct test 보강, `CanvasView.clear_scene()`의 `CanvasSceneResetService` 추출과 reset lifecycle/factory seam 고정
- 이번에 닫은 항목에 추가: `SceneItemController.attach_scene_item()` seam 추가, `SceneDecorationService` / `CanvasNoteController` / `StructureBuildService`의 runtime scene item register를 `scene_item_access.attach_scene_item()`으로 통일, controller-first / wrapper-fallback access contract 고정
- 이번에 닫은 항목에 추가: `BondRenderer` ring/double/bold variant matrix direct test 보강과 `CanvasView` projection/planar/rotation fallback helper direct test 보강
- 이번에 닫은 항목에 추가: `graphics_items` no-select paint + atom hit-bound contract direct test, `structure_benzene_logic` invalid attachment fallback direct test, `bond_graphics_logic` non-selectable fallback direct test, `template_insert_logic` invalid internal plan guard direct test, `BenzenePreviewService` inner-bond fallback direct test
- 지금 바로 손대야 할 곳: `preview_scene_renderer` / `scene_clipboard_logic` / `scene_delete_logic`
- 그 다음 구조 후보: `canvas_move_controller` / `text_tool_logic` / `main_window_canvas_logic`
- targeted polish 후보: `handle_interaction_logic`, `hover_scene_renderer`, `main.py`, `perspective_drag_logic`, `tool_overlay_logic`
- 큰 리팩터링보다 targeted test 보강이 맞는 곳: 위 90~95%대 service/controller 모듈 전반
