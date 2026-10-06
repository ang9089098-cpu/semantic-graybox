# -*- coding: utf-8 -*-
"""
Blender Import & Instancing 헬퍼
================================

Cube3D 가 생성한 OBJ 1개를 Blender 에 import 하고, 같은 master 의 각 slot(guide)
transform 위치에 **인스턴스(linked duplicate)** 로 배치한다.

정책 (연구 의도)
---------------
- 생성 Mesh 는 master 당 **1번만** import 하고, slot 수만큼 인스턴스를 만든다.
  (동일 master → 동일 결과 → 인스턴스로 배치)
- guide 를 자동 삭제하지 않는다. 생성 Mesh 는 별도 "Generated" 컬렉션에 넣어
  guide 와 나란히 비교 가능하게 한다.
- 생성 Mesh 를 guide 안에 억지로 비균일 스케일하지 않는다. anchor/orientation 만 맞춘다.

이 모듈은 Blender 안에서만 의미가 있으나, bpy 없이 import 되어도 (테스트 목적)
NameError 가 나지 않도록 방어적으로 처리한다. 실제 함수 호출 시 bpy 가 없으면
명확한 RuntimeError 를 던진다.
"""

from __future__ import annotations

try:
    import bpy            # type: ignore
    from mathutils import Euler, Vector  # type: ignore
    _HAS_BPY = True
except Exception:  # pragma: no cover - 블렌더 밖
    bpy = None
    Euler = None
    Vector = None
    _HAS_BPY = False


def _require_bpy():
    if not _HAS_BPY:
        raise RuntimeError("blender_import 는 Blender 안에서만 실행할 수 있습니다 (bpy 없음).")


def get_or_create_collection(name: str):
    """이름으로 컬렉션을 얻거나 새로 만들어 씬에 링크한다."""
    _require_bpy()
    coll = bpy.data.collections.get(name)
    if coll is None:
        coll = bpy.data.collections.new(name)
        bpy.context.scene.collection.children.link(coll)
    return coll


def import_obj(obj_path: str):
    """
    OBJ 를 import 하고 import 된 최상위 오브젝트들을 반환한다.
    Blender 4.3+/5.x 의 `bpy.ops.wm.obj_import` 를 사용한다.
    """
    _require_bpy()
    before = set(bpy.context.scene.objects)
    bpy.ops.wm.obj_import(filepath=obj_path)
    after = set(bpy.context.scene.objects)
    return [o for o in after - before]


def _apply_transform(obj, transform: dict):
    """slot transform dict(location/rotation_euler/scale) 를 오브젝트에 적용한다."""
    loc = transform.get("location", [0.0, 0.0, 0.0])
    rot = transform.get("rotation_euler", [0.0, 0.0, 0.0])
    scl = transform.get("scale", [1.0, 1.0, 1.0])
    obj.location = Vector((loc[0], loc[1], loc[2]))
    obj.rotation_euler = Euler((rot[0], rot[1], rot[2]), "XYZ")
    obj.scale = Vector((scl[0], scl[1], scl[2]))


def place_master_instances(obj_path: str, master: dict,
                           generated_collection_name: str = "Generated"):
    """Place one unique slot or repeated master slots; clean only this failed import."""
    _require_bpy()
    before = set(bpy.data.objects)
    try:
        return _place_instances(obj_path, master, generated_collection_name)
    except Exception:
        for obj in set(bpy.data.objects) - before:
            mesh = obj.data if obj.type == "MESH" else None
            bpy.data.objects.remove(obj, do_unlink=True)
            if mesh and mesh.users == 0:
                bpy.data.meshes.remove(mesh)
        raise


def _place_instances(obj_path: str, master: dict, generated_collection_name: str):
    """
    생성 OBJ 를 1번 import → master 의 각 slot transform 에 linked-duplicate 배치.

    파라미터
    --------
    obj_path : Cube3D 가 만든 .obj 경로
    master   : blueprint 의 master_part dict (master_id, slots[...] 포함)
    generated_collection_name : 생성물이 들어갈 컬렉션 이름 (guide 와 분리)

    반환: 생성된 인스턴스 오브젝트 리스트.

    동작
    ----
    1. OBJ import → 여러 파트면 하나로 join (mesh 데이터 1개 확보).
    2. 이 mesh 데이터를 공유하는 linked duplicate 를 slot 수만큼 생성.
    3. 각 인스턴스를 slot transform 에 배치하고 Generated 컬렉션에 링크.
    (기존 guide 는 건드리지 않는다.)
    """
    _require_bpy()
    gen_coll = get_or_create_collection(generated_collection_name)

    imported = import_obj(obj_path)
    # Explicit ownership survives linked copies and partial import failures.
    for obj in imported:
        obj["semantic_graybox_owner"] = "semantic_graybox_v02"
        obj["semantic_graybox_generated"] = True
        obj["generation_unit_id"] = master.get("master_id", "Master")
    if not imported:
        raise RuntimeError("OBJ import 결과가 비어있습니다: {0}".format(obj_path))

    # 여러 파트로 쪼개져 들어오면 하나로 합쳐 단일 mesh 데이터 확보
    bpy.ops.object.select_all(action="DESELECT")
    for o in imported:
        o.select_set(True)
    bpy.context.view_layer.objects.active = imported[0]
    if len(imported) > 1:
        bpy.ops.object.join()
    base = bpy.context.view_layer.objects.active

    master_id = master.get("master_id", "Master")
    slots = master.get("slots", [])

    # 원본 base 오브젝트를 씬 컬렉션에서 떼고 Generated 로 옮긴다.
    for c in list(base.users_collection):
        c.objects.unlink(base)

    instances = []
    if not slots:
        # slot 정보가 없으면 base 하나만 배치
        base.name = "{0}_Generated".format(master_id)
        gen_coll.objects.link(base)
        return [base]

    # 첫 slot 은 base 자체를 사용, 나머지는 linked duplicate
    for idx, slot in enumerate(slots):
        if idx == 0:
            inst = base
        else:
            inst = base.copy()          # linked duplicate: mesh 데이터 공유 (inst.data 동일)
            # inst.data 는 base.data 를 공유 (obj.copy() 는 데이터를 링크로 공유)
        inst.name = "{0}_Generated_{1}".format(master_id, slot.get("name", idx))
        inst["source_guide_name"] = slot.get("name", "")
        _apply_transform(inst, slot.get("transform", {}))
        if inst.name not in gen_coll.objects:
            gen_coll.objects.link(inst)
        instances.append(inst)

    return instances