# -*- coding: utf-8 -*-
"""
Blender integration test: Cube3D 생성 OBJ → 4 instances 배치 검증.

이 테스트는 실제 Cube3D 를 실행하지 않는다. 이미 생성된 OBJ(Generated/output.obj)를
받아서 blender_import.place_master_instances 가:
  - OBJ 를 1번만 import 하고
  - Master_Leg 의 4개 slot transform 에 인스턴스를 배치하며
  - "Generated" 컬렉션에 넣고, 기존 guide 는 그대로 두는지
를 검증한다.

실행:
    & "C:\\Program Files\\Blender Foundation\\Blender 5.2\\blender.exe" `
        --background --python "tests\\blender_cube3d_import_test.py" -- <obj_path>
"""
import bpy
import bmesh
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(HERE)
sys.path.insert(0, PROJECT_ROOT)

import semantic_graybox_extractor as ext
from generation.blender_import import place_master_instances

# -- OBJ 경로: `--` 뒤 인자 또는 기본 Generated/output.obj --
argv = sys.argv
obj_path = None
if "--" in argv:
    extra = argv[argv.index("--") + 1:]
    if extra:
        obj_path = extra[0]
if obj_path is None:
    obj_path = os.path.join(PROJECT_ROOT, "Generated", "output.obj")

print("\n=== CUBE3D IMPORT TEST ===")
print("bpy:", bpy.app.version_string)
print("obj_path:", obj_path)
assert os.path.isfile(obj_path), "OBJ 가 없습니다: {0}".format(obj_path)

# -- 1) Desk_01 씬 구성 (다리 4개) + extractor 로 master 획득 --
bpy.ops.wm.read_factory_settings(use_empty=True)
desk = bpy.data.collections.new("Desk_01")
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

parts = ext.collect_parts(desk)
clusters = ext.cluster_parts(parts)
masters = clusters["master_parts"]
leg_master = [m for m in masters if m["source_group"] == "Leg"][0]
print("master:", leg_master["master_id"], "slots:", len(leg_master["slots"]))
assert len(leg_master["slots"]) == 4

# -- 2) 생성 OBJ import + 4 instance 배치 --
guides_before = set(o.name for o in desk.objects)
instances = place_master_instances(obj_path, leg_master, generated_collection_name="Generated")

# -- 3) 검증 --
print("\n=== VERIFY ===")
assert len(instances) == 4, "인스턴스 4개가 아님: {0}".format(len(instances))

gen_coll = bpy.data.collections.get("Generated")
assert gen_coll is not None, "Generated 컬렉션 없음"
assert len(gen_coll.objects) == 4, "Generated 컬렉션에 4개가 아님: {0}".format(len(gen_coll.objects))

# mesh 데이터 공유(instance) 확인: 모든 인스턴스가 같은 mesh 데이터를 참조
mesh_datas = set(o.data.name for o in instances)
assert len(mesh_datas) == 1, "인스턴스가 mesh 데이터를 공유하지 않음: {0}".format(mesh_datas)

# guide 가 그대로 남아있는지 (자동 삭제 안 함)
guides_after = set(o.name for o in desk.objects)
assert guides_before == guides_after, "guide 가 변경/삭제됨"

# 각 인스턴스가 해당 slot 위치에 배치됐는지 (location 대조)
slot_locs = {s["name"]: tuple(s["transform"]["location"]) for s in leg_master["slots"]}
for inst in instances:
    # 이름: "Master_Leg_Generated_<slotname>"
    slotname = inst.name.replace("Master_Leg_Generated_", "")
    expected = slot_locs.get(slotname)
    if expected is not None:
        actual = (round(inst.location.x, 4), round(inst.location.y, 4), round(inst.location.z, 4))
        assert actual == tuple(round(v, 4) for v in expected), \
            "{0} 위치 불일치: {1} != {2}".format(slotname, actual, expected)

print("Generated collection objects:", [o.name for o in gen_coll.objects])
print("shared mesh data:", list(mesh_datas))
print("guides intact:", sorted(guides_after))
print("CUBE3D IMPORT + 4 INSTANCES: PASSED")