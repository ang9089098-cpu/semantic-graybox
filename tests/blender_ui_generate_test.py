# -*- coding: utf-8 -*-
"""
Blender UI end-to-end test (실제 Cube3D generation 수행).

이 테스트는 GUI 클릭을 시뮬레이션한다:
  1. blender_ui.register() 로 패널/오퍼레이터 등록
  2. Desk 컬렉션(상판 + 다리 4개) 구성
  3. scene.semantic_graybox 에 target_collection=Desk, style="Rococo", generator="cube3d" 설정
  4. 패널/오퍼레이터가 실제로 등록됐는지 확인
  5. Generate 오퍼레이터를 **실제로 호출** → 진짜 Cube3D 생성 + import
  6. Generated 컬렉션에 Master_Leg 4 instance 배치, guide 유지 검증

실행 (실제 GPU 생성, 수분 소요):
    & "C:\\Program Files\\Blender Foundation\\Blender 5.2\\blender.exe" `
        --background --python "tests\\blender_ui_generate_test.py"
"""
import bpy
import bmesh
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(HERE)
sys.path.insert(0, PROJECT_ROOT)

import blender_ui
from generation.generator_adapters.cube3d_adapter import Cube3DConfig

print("\n=== UI GENERATE E2E TEST ===")
print("bpy:", bpy.app.version_string)

# --- 0) 실제 파이프라인이 사용할 출력 경로를 그대로 계산한다 ---
# (하드코딩된 Google Drive 경로 대신, adapter 가 실제로 쓰는 것과 동일한 방식으로
#  CUBE3D_OUTPUT 환경변수/관례 경로를 그대로 재사용 — production 코드와 동일 로직.)
_cfg = Cube3DConfig.from_env(base_dir=PROJECT_ROOT)
obj_path = os.path.join(_cfg.output_dir, "output.obj")
print("expected output path (from Cube3DConfig.from_env):", obj_path)

# --- 이전 산출물 제거 (GUI 트리거로 재생성됨을 증명) ---
if os.path.isfile(obj_path):
    os.remove(obj_path)
    print("removed old OBJ:", obj_path)

# --- 1) UI 등록 ---
blender_ui.register()
# PropertyGroup: Scene 에 붙었는지
assert hasattr(bpy.types.Scene, "semantic_graybox"), "PropertyGroup 미등록"
# Operator: 실제 호출 경로(bpy.ops.<category>.<name>) 로 확인 (문자열 검사 X)
assert hasattr(bpy.ops.semantic_graybox, "generate"), "Operator 미등록 (bpy.ops)"
# Operator 가 실제로 호출 가능한 상태인지 poll 로 확인
poll_ok = bpy.ops.semantic_graybox.generate.poll()
assert poll_ok, "Operator poll() 실패 (호출 불가 상태)"
# Panel: 등록된 Panel 서브클래스 목록에서 bl_idname 으로 확인 (dir 문자열 검사 X)
panel_ids = {c.bl_idname for c in bpy.types.Panel.__subclasses__()
             if hasattr(c, "bl_idname")}
assert "SEMANTICGRAYBOX_PT_panel" in panel_ids, "Panel 미등록"
print("UI registered: panel + operator(poll ok) + props OK")

# --- 2) Desk 씬 구성 ---
bpy.ops.wm.read_factory_settings(use_empty=True)

# read_factory_settings 후 재등록 필요 (scene 이 갈아엎힘)
# → PointerProperty 는 bpy.types.Scene 에 붙어있으므로 새 scene 에도 적용됨. 확인:
if not hasattr(bpy.context.scene, "semantic_graybox"):
    # 안전하게 재등록
    blender_ui.unregister()
    blender_ui.register()

desk = bpy.data.collections.new("Desk")
bpy.context.scene.collection.children.link(desk)
layer_coll = bpy.context.view_layer.layer_collection.children[desk.name]
bpy.context.view_layer.active_layer_collection = layer_coll

def add_box(name, size, location, parent=None):
    mesh = bpy.data.meshes.new(name)
    obj = bpy.data.objects.new(name, mesh)
    bm = bmesh.new(); bmesh.ops.create_cube(bm, size=1.0); bm.to_mesh(mesh); bm.free()
    obj.scale = size; obj.location = location
    if parent: obj.parent = parent
    desk.objects.link(obj)
    return obj

top = add_box("Top", (2.0, 1.0, 0.1), (0.0, 0.0, 1.0))
add_box("Leg_fl", (0.08, 0.08, 0.70), (-0.9, -0.4, 0.5), parent=top)
add_box("Leg_fr", (0.08, 0.08, 0.70), ( 0.9, -0.4, 0.5), parent=top)
add_box("Leg_bl", (0.08, 0.08, 0.70), (-0.9,  0.4, 0.5), parent=top)
add_box("Leg_br", (0.08, 0.08, 0.70), ( 0.9,  0.4, 0.5), parent=top)
bpy.context.view_layer.update()

guides_before = set(o.name for o in desk.objects)

# --- 3) 패널 입력값 설정 (GUI 에서 사용자가 입력하는 것과 동일) ---
props = bpy.context.scene.semantic_graybox
props.target_collection = desk
props.style_prompt = "Rococo"
props.generator = "cube3d"
print("panel input -> collection:", props.target_collection.name,
      "| style:", props.style_prompt, "| generator:", props.generator)

# --- 4) Generate 오퍼레이터 실제 호출 (GUI 버튼 클릭과 동일) ---
print("\n[calling operator] semantic_graybox.generate ... (실제 Cube3D 생성, 수분 소요)")
res = bpy.ops.semantic_graybox.generate()
print("operator result:", res)

# --- 5) 검증 ---
print("\n=== VERIFY ===")
assert res == {"FINISHED"}, "operator 가 FINISHED 아님: {0}".format(res)
assert os.path.isfile(obj_path), "OBJ 재생성 안 됨: {0}".format(obj_path)

gen_coll = bpy.data.collections.get("Generated")
assert gen_coll is not None, "Generated 컬렉션 없음"
assert len(gen_coll.objects) == 4, "instance 4개 아님: {0}".format(len(gen_coll.objects))

mesh_datas = set(o.data.name for o in gen_coll.objects)
assert len(mesh_datas) == 1, "instance mesh 공유 안 됨: {0}".format(mesh_datas)

guides_after = set(o.name for o in desk.objects)
assert guides_before == guides_after, "guide 변경/삭제됨"

print("OBJ:", obj_path, "size:", os.path.getsize(obj_path))
print("Generated instances:", [o.name for o in gen_coll.objects])
print("guides intact:", sorted(guides_after))
print("UI GENERATE E2E: PASSED")

blender_ui.unregister()