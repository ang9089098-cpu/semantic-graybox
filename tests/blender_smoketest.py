# -*- coding: utf-8 -*-
"""
Headless smoke test: Blender 5.2.2 안에서 semantic_graybox_extractor 를 실제로 구동.
- 빈 씬에 'Desk_01' 컬렉션을 만들고 Top + 다리 4개(Leg_fl/fr/bl/br)를 배치한다.
- 활성 컬렉션을 Desk_01 로 지정한 뒤 extractor.main() 호출.
- 결과 blueprint 의 핵심 필드를 검증한다.
"""
import bpy
import os
import sys

# 이 테스트는 tests/ 하위에 있으므로, production 모듈이 있는 프로젝트 루트(부모 폴더)를
# import path 에 추가한다. (production 코드는 이 테스트를 import/실행하지 않는다 — 분리 유지.)
HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(HERE)
sys.path.insert(0, PROJECT_ROOT)

import semantic_graybox_extractor as ext

print("\n=== BLENDER RUNTIME ===")
print("bpy version:", bpy.app.version_string)
print("_HAS_BPY   :", ext._HAS_BPY)

# ---- 1) 깨끗한 씬 준비 ----
bpy.ops.wm.read_factory_settings(use_empty=True)

# ---- 2) Desk_01 컬렉션 생성 & 활성화 ----
desk = bpy.data.collections.new("Desk_01")
bpy.context.scene.collection.children.link(desk)
desk["style"] = "modern"          # custom property → metadata 검증용

# 활성 레이어 컬렉션을 Desk_01 로 지정
layer_coll = bpy.context.view_layer.layer_collection.children[desk.name]
bpy.context.view_layer.active_layer_collection = layer_coll

def add_box(name, size, location, parent=None):
    mesh = bpy.data.meshes.new(name)
    obj = bpy.data.objects.new(name, mesh)
    # 큐브 지오메트리 생성
    import bmesh
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    bm.to_mesh(mesh)
    bm.free()
    obj.scale = size
    obj.location = location
    if parent:
        obj.parent = parent
    desk.objects.link(obj)
    return obj

# 상판 (unique part)
top = add_box("Top", (2.0, 1.0, 0.1), (0.0, 0.0, 1.0))

# 다리 4개 (동일 크기 → 단일 마스터 + EQUAL_DIMENSION 기대)
add_box("Leg_fl", (0.1, 0.1, 1.0), (-0.9, -0.4, 0.5), parent=top)
add_box("Leg_fr", (0.1, 0.1, 1.0), ( 0.9, -0.4, 0.5), parent=top)
add_box("Leg_bl", (0.1, 0.1, 1.0), (-0.9,  0.4, 0.5), parent=top)
add_box("Leg_br", (0.1, 0.1, 1.0), ( 0.9,  0.4, 0.5), parent=top)

# dimensions 갱신을 위해 depsgraph evaluate
bpy.context.view_layer.update()

# 출력 경로를 임시 폴더로 고정 (드라이브 경로 이슈 회피)
import tempfile
ext.CONFIG["OUTPUT_DIR"] = tempfile.gettempdir()

# ---- 3) 실제 파이프라인 실행 ----
bp = ext.main()

# ---- 4) 검증 ----
print("\n=== VERIFY ===")
assert bp is not None, "blueprint 가 None"
assert bp["entity_type"] == "Desk", bp["entity_type"]
assert bp["instance_id"] == "01", bp["instance_id"]
assert bp["metadata"].get("style") == "modern", bp["metadata"]
assert bp["stats"]["total_mesh_parts"] == 5, bp["stats"]
assert bp["stats"]["unique_count"] == 1, bp["stats"]      # Top
assert bp["stats"]["master_count"] == 1, bp["stats"]      # Leg master
master = bp["components"]["master_parts"][0]
assert master["instance_count"] == 4, master["instance_count"]
assert master["constraints"][0]["type"] == "EQUAL_DIMENSION"
assert master.get("dimension_equal_verified") is True
assert len(bp["topology"]) == 4, bp["topology"]           # 4 legs parented to Top

print("ALL ASSERTIONS PASSED ✅")
print("master_id:", master["master_id"], "count:", master["instance_count"])