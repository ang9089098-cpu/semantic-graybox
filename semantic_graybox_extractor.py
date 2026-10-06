# -*- coding: utf-8 -*-
"""
Relational Semantic Graybox Extractor
=====================================

블렌더 아웃라이너의 "활성 Collection" 계층을 파싱하여, AI 조립(Assembly) 에이전트가
소비할 수 있는 "시맨틱 청사진(Semantic Blueprint)" JSON을 추출하는 bpy 스크립트.

핵심 아이디어 (Relational Semantic Graybox)
-------------------------------------------
- 4개의 다리를 "4번 만들어라"가 아니라 "다리 1개 마스터 + 관계 제약(EQUAL_DIMENSION) +
  슬롯별 배치 좌표(slots)"로 압축해서 표현한다.
- 앞/뒤 다리 크기가 유의미하게 다르면 Front/Back 서브마스터로 자동 분기하고, 두 그룹
  사이의 비율(RATIO) 관계를 기록한다.

파이프라인
----------
    main()
      └─ get_active_collection()          # 활성 컬렉션 안전 획득
      └─ parse_entity_context()           # 이름/커스텀 프로퍼티 → 엔티티 메타데이터
      └─ collect_parts()                  # MESH 순회 → World Transform + 4종 앵커
      └─ build_topology()                 # parent-child 엣지 리스트
      └─ cluster_parts()                  # 접두사(그룹 키) 기준 클러스터링
      │     └─ compare_dimensions()       # tolerance 내 동일 판정
      │     └─ evaluate_cluster_constraints()  # EQUAL_DIMENSION / Front-Back 분기 + RATIO
      └─ assemble_blueprint()             # 최종 청사진 dict
      └─ dump_blueprint()                 # .json 파일 저장 + 콘솔 미리보기

실행: 블렌더 텍스트 에디터에 붙여넣고 ▶ Run Script.
      (블렌더 밖에서도 import 가능 - bpy 미존재 시 로직 단위 테스트만 가능)
"""

import json
import os
import tempfile

# ---------------------------------------------------------------------------
# bpy / mathutils 는 블렌더 안에서만 존재한다. 블렌더 밖(순수 파이썬 테스트)에서도
# 클러스터링/비교/조립 같은 순수 로직을 검증할 수 있도록 임포트를 방어적으로 처리한다.
# ---------------------------------------------------------------------------
try:
    import bpy            # type: ignore
    from mathutils import Vector  # type: ignore
    _HAS_BPY = True
except Exception:  # pragma: no cover - 블렌더 밖
    bpy = None
    Vector = None
    _HAS_BPY = False


# ===========================================================================
# [CONFIG] 모든 튜닝 파라미터를 한곳에 노출한다. 조립 파이프라인/네이밍 컨벤션에
#          맞게 이 블록만 수정하면 된다.
# ===========================================================================
CONFIG = {
    # ── 그룹 키 파싱 ────────────────────────────────────────────────────
    # 오브젝트 이름을 이 구분자로 쪼갠 뒤 "첫 토큰"을 그룹 키로 사용한다.
    #   "Leg_fl" -> group_key="Leg", suffix="fl"
    "GROUP_KEY_SEP": "_",

    # ── 동등성(클러스터링) 판정 ─────────────────────────────────────────
    # 그룹 평균 dimensions 대비 각 파트의 상대 오차가 이 값 이내이면 "동일 크기"로
    # 보고 하나의 마스터로 묶는다. 0.05 = 5%.
    "DIMENSION_TOLERANCE": 0.05,

    # ── 서브마스터 분기 임계값 ──────────────────────────────────────────
    # 한 그룹 안에서 크기 편차(최대/최소 비율 - 1)가 이 값을 초과하면 단일 마스터로
    # 묶지 않고 Front/Back 서브마스터로 자동 분기한다. 0.15 = 15%.
    "SUBMASTER_SPLIT_THRESHOLD": 0.15,

    # ── 방향 접미사 시맨틱 맵 ───────────────────────────────────────────
    # 접미사 문자 → 의미. 서브마스터 분기 시 Front/Back 라벨 명명에 사용한다.
    "DIRECTION_SUFFIX_MAP": {
        "f": "Front",
        "b": "Back",
        "l": "Left",
        "r": "Right",
    },

    # ── 출력 ────────────────────────────────────────────────────────────
    # None 이면 .blend 파일 옆에 저장. 저장 안 된 씬이면 tempfile 경로로 fallback.
    "OUTPUT_DIR": None,
    "OUTPUT_SUFFIX": "_semantic_blueprint.json",
    "JSON_INDENT": 2,
    "FLOAT_PRECISION": 6,        # 좌표 반올림 자릿수 (JSON 가독성)
    "PRINT_PREVIEW": True,       # System Console 에 pretty-print 미리보기
}


# ===========================================================================
# 유틸리티
# ===========================================================================
def _round_list(values, precision):
    """리스트(또는 벡터-유사)를 지정 자릿수로 반올림한 순수 float 리스트로 변환."""
    return [round(float(v), precision) for v in values]


def _safe_ratio(a, b):
    """0 나눗셈을 방지하는 비율 계산 헬퍼."""
    if abs(b) < 1e-9:
        return 0.0
    return a / b


# ===========================================================================
# [Task 1 스캐폴딩] 함수 시그니처 — 아래에서 순차적으로 구현된다.
# ===========================================================================

def get_config():
    """현재 CONFIG dict 반환 (테스트/디버그용 단일 진입점)."""
    return CONFIG


def main():
    """스크립트 진입점 — 전체 파이프라인을 순서대로 실행한다."""
    print("=" * 70)
    print(" Relational Semantic Graybox Extractor")
    print("=" * 70)
    print("[CONFIG]")
    for k, v in get_config().items():
        print("   {0:24s}: {1}".format(k, v))

    if not _HAS_BPY:
        print("\n[!] bpy 를 찾을 수 없습니다. 이 스크립트는 블렌더 안에서 실행하세요.")
        print("    (블렌더 밖에서는 순수 로직 단위 테스트만 가능합니다.)")
        return None

    # 1) 활성 컬렉션 획득
    collection = get_active_collection()
    if collection is None:
        return None

    # 2) 엔티티 컨텍스트(이름/스타일 등)
    entity = parse_entity_context(collection)

    # 3) 파트 추출 (MESH only, world transform + 4종 앵커)
    parts = collect_parts(collection)
    if not parts:
        print("[!] 컬렉션 '{0}' 안에 MESH 오브젝트가 없습니다.".format(collection.name))
        return None

    # 4) 토폴로지 (parent-child)
    topology = build_topology(parts)

    # 5) 클러스터링 → 마스터/서브마스터/제약
    clusters = cluster_parts(parts)

    # 6) 청사진 조립 & 덤프
    blueprint = assemble_blueprint(entity, parts, clusters, topology)
    path = dump_blueprint(blueprint)
    print("\n[OK] Semantic blueprint 저장 완료 → {0}".format(path))
    return blueprint


# ===========================================================================
# [Task 2] Active Collection 획득 + 엔티티 컨텍스트 파싱
# ===========================================================================

def get_active_collection():
    """
    아웃라이너에서 "활성화된" 컬렉션을 안전하게 획득한다.

    - bpy.context.view_layer.active_layer_collection.collection 를 사용한다.
    - 활성 컬렉션이 없거나 최상위 Scene Collection 뿐이면 명확히 안내하고 None 반환.
    """
    view_layer = bpy.context.view_layer
    active_layer_coll = getattr(view_layer, "active_layer_collection", None)
    if active_layer_coll is None or active_layer_coll.collection is None:
        print("[!] 활성 컬렉션을 찾을 수 없습니다. 아웃라이너에서 타겟 컬렉션을 클릭해 활성화하세요.")
        return None

    collection = active_layer_coll.collection

    # Scene Collection(최상위 마스터)은 엔티티가 아니므로 방어적으로 안내.
    scene_master = bpy.context.scene.collection
    if collection == scene_master:
        print("[!] 현재 활성 컬렉션이 Scene Collection(최상위)입니다.")
        print("    Desk_01 같은 실제 엔티티 컬렉션을 아웃라이너에서 활성화하세요.")
        return None

    print("\n[STEP] 활성 컬렉션: '{0}' (objects={1})".format(
        collection.name, len(collection.objects)))
    return collection


def parse_entity_context(collection):
    """
    컬렉션 이름과 Custom Property 를 엔티티 메타데이터로 변환한다.

    이름 파싱 규칙 ("_" 기준):
        "Desk_01"   -> entity_type="Desk", instance_id="01"
        "Chair"     -> entity_type="Chair", instance_id=None
        "Desk_A_02" -> entity_type="Desk", instance_id="A_02" (첫 토큰만 타입)

    Custom Property:
        collection.items() 순회. 단, "_RNA_UI" 및 "_"로 시작하는 내부 키는 제외.
    """
    sep = CONFIG["GROUP_KEY_SEP"]
    name = collection.name
    tokens = name.split(sep, 1)
    entity_type = tokens[0]
    instance_id = tokens[1] if len(tokens) > 1 else None

    metadata = {}
    # collection.items() → (key, value) 쌍. ID Custom Property 를 순회한다.
    for key, value in collection.items():
        if key == "_RNA_UI" or key.startswith("_"):
            continue  # 블렌더 내부 UI 메타데이터는 스킵
        metadata[key] = _coerce_prop_value(value)

    entity = {
        "entity_type": entity_type,
        "instance_id": instance_id,
        "source_collection": name,
        "metadata": metadata,
    }
    print("[STEP] 엔티티 컨텍스트: type='{0}', instance='{1}', metadata={2}".format(
        entity_type, instance_id, metadata))
    return entity


def _coerce_prop_value(value):
    """
    블렌더 Custom Property 값을 JSON 직렬화 가능한 순수 파이썬 타입으로 변환.
    (IDPropertyArray, IDPropertyGroup 등은 list/dict 로 풀어준다.)
    """
    # 배열류(IDPropertyArray)는 iterable → list
    try:
        if hasattr(value, "to_list"):
            return value.to_list()
        if hasattr(value, "to_dict"):
            return value.to_dict()
    except Exception:
        pass
    # 기본 스칼라(str/int/float/bool)는 그대로
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    # 알 수 없는 타입은 문자열화
    try:
        return list(value)
    except Exception:
        return str(value)


# ===========================================================================
# [Task 3] 파트 추출 — World Transform + 4종 앵커 (bbox_bounds_world 포함)
# ===========================================================================

def get_world_transform(obj):
    """
    obj.matrix_world 를 분해해 world-space loc/rot/scale 을 반환한다.

    회전은 Euler(라디안, XYZ) 로 기록한다.
    """
    mw = obj.matrix_world
    loc = mw.translation
    rot = mw.to_euler()      # Euler XYZ (radians)
    scl = mw.to_scale()
    p = CONFIG["FLOAT_PRECISION"]
    return {
        "location": _round_list(loc, p),
        "rotation_euler": _round_list([rot.x, rot.y, rot.z], p),
        "scale": _round_list(scl, p),
    }


def _world_bbox_corners(obj):
    """
    obj.bound_box (로컬 8코너) 를 matrix_world 로 변환한 world-space 코너 리스트.
    """
    mw = obj.matrix_world
    return [mw @ Vector(corner) for corner in obj.bound_box]


def get_world_bbox_center(obj):
    """world-space bounding box 8코너의 평균 = 중심점."""
    corners = _world_bbox_corners(obj)
    center = Vector((0.0, 0.0, 0.0))
    for c in corners:
        center += c
    center /= len(corners)
    return _round_list(center, CONFIG["FLOAT_PRECISION"])


def get_world_bbox_bounds(obj):
    """
    world-space 축별 min/max 바운즈. 체결(접면) 정렬 계산에 사용.

    반환: {"min": [x,y,z], "max": [x,y,z]}
    """
    corners = _world_bbox_corners(obj)
    xs = [c.x for c in corners]
    ys = [c.y for c in corners]
    zs = [c.z for c in corners]
    p = CONFIG["FLOAT_PRECISION"]
    return {
        "min": _round_list([min(xs), min(ys), min(zs)], p),
        "max": _round_list([max(xs), max(ys), max(zs)], p),
    }


def build_anchor_points(obj):
    """
    한 파트에 대한 4종 앵커를 모두 기록해 조립 에이전트가 선택하도록 한다.

        origin_world       : 오브젝트 origin 의 world 좌표 (matrix_world.translation)
        bbox_center_world  : world bbox 8코너 평균
        dimensions         : obj.dimensions (world-scale 반영 bbox 크기)
        bbox_bounds_world  : {min, max} — 접면 정렬용
    """
    p = CONFIG["FLOAT_PRECISION"]
    return {
        "origin_world": _round_list(obj.matrix_world.translation, p),
        "bbox_center_world": get_world_bbox_center(obj),
        "dimensions": _round_list(obj.dimensions, p),
        "bbox_bounds_world": get_world_bbox_bounds(obj),
    }


def extract_part(obj):
    """
    단일 MESH 오브젝트 → 파트 dict.
    (그룹 키/접미사는 이후 cluster 단계에서 이름으로 파싱하므로 여기서도 미리 계산해 둔다.)
    """
    group_key, suffix = extract_group_key(obj.name)
    direction = parse_direction_suffix(suffix)
    return {
        "name": obj.name,
        "parent": obj.parent.name if obj.parent is not None else None,
        "group_key": group_key,
        "suffix": suffix,
        "direction": direction,          # {"front_back":..., "left_right":...} or {}
        "transform": get_world_transform(obj),
        "anchor_points": build_anchor_points(obj),
    }


def collect_parts(collection):
    """
    컬렉션 내 오브젝트를 순회하며 MESH 만 파트로 추출한다.
    (스케일 0 등 degenerate 오브젝트는 경고만 남기고 그대로 기록 — 정보 손실 방지.)
    """
    parts = []
    skipped = []
    for obj in collection.objects:
        if obj.type != "MESH":
            skipped.append("{0}({1})".format(obj.name, obj.type))
            continue
        part = extract_part(obj)
        # degenerate 스케일 경고 (진단용)
        if any(abs(d) < 1e-9 for d in part["anchor_points"]["dimensions"]):
            print("   [warn] '{0}' 의 dimension 이 0 에 가깝습니다.".format(obj.name))
        parts.append(part)

    print("[STEP] 파트 추출: MESH {0}개 수집".format(len(parts)))
    if skipped:
        print("        (비-MESH {0}개 스킵: {1})".format(len(skipped), ", ".join(skipped)))
    return parts


# ===========================================================================
# [Task 4] 토폴로지 — Parent-Child 엣지 리스트
# ===========================================================================

def build_topology(parts):
    """
    파트 간 parent-child 관계를 엣지 리스트로 기록한다.

    - 컬렉션 내부에 부모가 존재하는 경우만 엣지로 남긴다.
    - 부모가 컬렉션 밖(또는 없음)이면 external_parent 로 표시하여 정보만 보존한다.
    """
    names_in_scope = {p["name"] for p in parts}
    edges = []
    external = []
    for p in parts:
        parent = p["parent"]
        if parent is None:
            continue
        if parent in names_in_scope:
            edges.append({"parent": parent, "child": p["name"]})
        else:
            external.append({"child": p["name"], "external_parent": parent})

    print("[STEP] 토폴로지: 내부 엣지 {0}개, 외부 부모 {1}개".format(
        len(edges), len(external)))
    return {"edges": edges, "external_parents": external}


# ===========================================================================
# [Task 5] 그룹 키 / 방향 접미사 파서 (Fallback 포함)
# ===========================================================================

def extract_group_key(name):
    """
    오브젝트 이름 → (group_key, suffix).

    규칙:
        "Leg_fl"    -> ("Leg", "fl")
        "Leg_Front" -> ("Leg", "Front")
        "Top"       -> ("Top", "")            # 접미사 없음 → 단일 파트 후보
        "Drawer_01" -> ("Drawer", "01")       # 숫자 접미사도 그룹 키는 Drawer

    Fallback:
        - 구분자가 없으면 이름 전체가 group_key, suffix="".
        - 블렌더 자동 넘버링(".001") 은 group_key 판정에서 무시한다.
    """
    sep = CONFIG["GROUP_KEY_SEP"]
    # 블렌더 중복 넘버링 ".001" 제거
    base = name.split(".")[0]
    if sep in base:
        key, suffix = base.split(sep, 1)
        return key, suffix
    return base, ""


def parse_direction_suffix(suffix):
    """
    방향 접미사를 시맨틱으로 해석한다.

        "fl" -> {"front_back": "Front", "left_right": "Left"}
        "br" -> {"front_back": "Back",  "left_right": "Right"}
        "01" -> {}   # 숫자형/미인식 → 방향 정보 없음 (Fallback)

    front/back(f/b) 와 left/right(l/r) 를 각각 최대 1글자씩 인식한다.
    """
    dmap = CONFIG["DIRECTION_SUFFIX_MAP"]
    result = {}
    if not suffix:
        return result

    low = suffix.lower()
    # 숫자형 접미사는 방향 아님
    if low.isdigit():
        return result

    for ch in low:
        meaning = dmap.get(ch)
        if meaning in ("Front", "Back") and "front_back" not in result:
            result["front_back"] = meaning
        elif meaning in ("Left", "Right") and "left_right" not in result:
            result["left_right"] = meaning
    return result


# ===========================================================================
# [Task 6 & 7] 클러스터링 + Dimension 비교 + 서브마스터 분기 + 제약
# ===========================================================================

def _sorted_dims(dimensions):
    """
    비교 안정성을 위해 dimension 성분을 내림차순 정렬한다.
    (오브젝트가 회전돼 있어도 축 순서에 흔들리지 않고 '형태 크기'로 비교하기 위함.)
    """
    return sorted([abs(d) for d in dimensions], reverse=True)


def compare_dimensions(dims_a, dims_b, tolerance):
    """
    두 dimension 벡터가 tolerance(상대 오차) 이내로 동일한지 판정한다.

    각 성분(정렬 후)에 대해 |a-b| / max(|a|,|b|) 가 모두 tolerance 이하이면 True.
    """
    sa, sb = _sorted_dims(dims_a), _sorted_dims(dims_b)
    for a, b in zip(sa, sb):
        denom = max(abs(a), abs(b), 1e-9)
        if abs(a - b) / denom > tolerance:
            return False
    return True


def _group_max_deviation(members):
    """
    그룹 내 크기 편차 = (최대 볼륨 대리값 / 최소 볼륨 대리값) - 1.

    볼륨 대리값으로 dimension 성분의 곱(정렬 무관)을 사용한다.
    분기 임계값(SUBMASTER_SPLIT_THRESHOLD) 판정에 쓰인다.
    """
    volumes = []
    for m in members:
        dims = m["anchor_points"]["dimensions"]
        vol = 1.0
        for d in dims:
            vol *= max(abs(d), 1e-9)
        volumes.append(vol)
    vmin, vmax = min(volumes), max(volumes)
    return _safe_ratio(vmax, vmin) - 1.0


def _mean_dimensions(members):
    """그룹 멤버들의 dimension 평균 벡터 (대표 크기)."""
    n = len(members)
    acc = [0.0, 0.0, 0.0]
    for m in members:
        dims = m["anchor_points"]["dimensions"]
        for i in range(3):
            acc[i] += dims[i]
    return [v / n for v in acc]


def _make_slot(part):
    """
    마스터 파트의 인스턴스 슬롯 — 배치 좌표(World Transform)와 앵커를 모두 보존한다.
    (조립 에이전트가 각 다리를 어디에 놓을지 알 수 있도록.)
    """
    return {
        "name": part["name"],
        "transform": part["transform"],
        "anchor_points": part["anchor_points"],
        "direction": part["direction"],
    }


def _build_master(master_id, group_key, members, tolerance):
    """단일 마스터 파트 dict 생성 (slots + EQUAL_DIMENSION 제약)."""
    p = CONFIG["FLOAT_PRECISION"]
    return {
        "master_id": master_id,
        "source_group": group_key,
        "instance_count": len(members),
        "representative_dimensions": _round_list(_mean_dimensions(members), p),
        "slots": [_make_slot(m) for m in members],
        "constraints": [
            {"type": "EQUAL_DIMENSION", "tolerance": tolerance,
             "applies_to": [m["name"] for m in members]}
        ],
    }


def _group_by_size_signature(members, tolerance):
    """
    멤버들을 **실제 크기 유사도**(compare_dimensions, 기존 tolerance 메커니즘) 기준으로
    묶는다. 방향 접미사(FL/FR/BL/BR)나 정렬 순위가 아니라, 각 멤버의 dimensions 가
    이미 형성된 그룹의 대표값과 tolerance 이내로 같은지를 보고 그룹을 결정한다
    (greedy: 먼저 나온 순서대로 맞는 그룹에 배정하거나 새 그룹을 만든다).

    이 함수는 "geometry identity" 를 결정한다 — 몇 개의 서로 다른 그룹으로
    나뉘어도 상관없다(고정된 2분할을 강제하지 않음). placement/anchor 정보
    (위치, 방향 접미사, 회전)는 이 판정에 전혀 사용하지 않는다.

    반환: [[member, ...], [member, ...], ...]  (크기 순으로 정렬된 그룹 리스트, 큰 것부터)
    """
    def vol(m):
        v = 1.0
        for d in m["anchor_points"]["dimensions"]:
            v *= max(abs(d), 1e-9)
        return v

    groups = []          # [{"rep_dims": [...], "members": [...]}]
    for m in members:
        dims = m["anchor_points"]["dimensions"]
        placed = False
        for g in groups:
            if compare_dimensions(dims, g["rep_dims"], tolerance):
                g["members"].append(m)
                # 대표값을 그룹 평균으로 갱신 (그룹이 커질수록 안정적인 기준이 되도록)
                g["rep_dims"] = _mean_dimensions(g["members"])
                placed = True
                break
        if not placed:
            groups.append({"rep_dims": list(dims), "members": [m]})

    groups.sort(key=lambda g: vol({"anchor_points": {"dimensions": g["rep_dims"]}}), reverse=True)
    return [g["members"] for g in groups]


def _label_size_groups(group_key, size_groups):
    """
    크기 기준으로 이미 결정된 size_groups(geometry identity) 에 사람이 읽을 라벨을
    붙인다. 각 그룹의 멤버들이 **공통된 방향 접미사**(front_back)를 가지고 있으면
    그 방향으로 라벨링하고(예: "Leg_Front"), 아니면 크기 순위로 Large/Small/그
    이상은 순번을 붙인다. 방향 라벨은 여기서 "이름"에만 쓰이고, 그룹을 나누는
    기준(geometry identity)에는 전혀 관여하지 않는다 — 즉 이미 정해진
    size_groups 를 재분할하거나 합치지 않는다.

    반환: {label: [members...], ...}  (evaluate_cluster_constraints 의 buckets 형태와 동일)
    """
    result = {}
    used_labels = set()

    def label_for(members):
        fb_votes = {}
        for m in members:
            fb = m["direction"].get("front_back")
            if fb:
                fb_votes[fb] = fb_votes.get(fb, 0) + 1
        if fb_votes and len(fb_votes) == 1:
            # 이 그룹의 멤버 전원이 하나의 방향으로 일치할 때만 방향으로 명명한다.
            only_direction = next(iter(fb_votes))
            candidate = "{0}_{1}".format(group_key, only_direction)
            if candidate not in used_labels:
                return candidate
        return None

    size_rank_names = ["Large", "Small"] + ["Size{0}".format(i) for i in range(3, 100)]
    for idx, members in enumerate(size_groups):
        label = label_for(members)
        if label is None:
            if len(size_groups) == 2:
                # 2개 그룹일 때만 기존과 동일한 Large/Small 명명 유지 (하위 호환)
                label = "{0}_{1}".format(group_key, size_rank_names[idx])
            else:
                label = "{0}_{1}".format(group_key, size_rank_names[idx]
                                          if idx < 2 else "Size{0}".format(idx + 1))
        used_labels.add(label)
        result[label] = members
    return result


def evaluate_cluster_constraints(group_key, members):
    """
    한 그룹(group_key)에 대해 마스터/서브마스터와 제약을 산출한다.

    반환: (masters, relations)
        masters   : master_part dict 리스트 (1개 또는 서브마스터 2개+)
        relations : 서브마스터 간 관계(RATIO 등) 리스트
    """
    tolerance = CONFIG["DIMENSION_TOLERANCE"]
    split_th = CONFIG["SUBMASTER_SPLIT_THRESHOLD"]

    # (a) 그룹 편차 계산 → 분기 필요 여부 판단
    deviation = _group_max_deviation(members)

    if deviation <= split_th:
        # (b) 균일 그룹: 단일 마스터로 압축
        master_id = "Master_{0}".format(group_key)
        master = _build_master(master_id, group_key, members, tolerance)
        # 실제로 tolerance 안에서 동일한지 재확인해 신뢰도 플래그 부여
        mean = _mean_dimensions(members)
        all_equal = all(
            compare_dimensions(m["anchor_points"]["dimensions"], mean, tolerance)
            for m in members
        )
        master["dimension_equal_verified"] = all_equal
        return [master], []

    # (c) 유의미한 편차: 실제 크기 유사도(compare_dimensions) 기준으로 geometry
    #     master 를 분리한다. 방향 접미사/anchor 는 이름(라벨)에만 쓰이고,
    #     그룹을 나누는 기준에는 관여하지 않는다 (placement != geometry identity).
    size_groups = _group_by_size_signature(members, tolerance)
    buckets = _label_size_groups(group_key, size_groups)
    masters = []
    for sub_label, sub_members in buckets.items():
        masters.append(_build_master(sub_label, group_key, sub_members, tolerance))

    # (d) 서브마스터 간 RATIO(비율) 관계 기록 — 계층적 제약
    relations = []
    labels = list(buckets.keys())
    for i in range(len(labels)):
        for j in range(i + 1, len(labels)):
            a_mean = _mean_dimensions(buckets[labels[i]])
            b_mean = _mean_dimensions(buckets[labels[j]])
            ratio = [round(_safe_ratio(a_mean[k], b_mean[k]),
                           CONFIG["FLOAT_PRECISION"]) for k in range(3)]
            relations.append({
                "type": "RATIO",
                "relation": "PROPORTIONAL",
                "between": [labels[i], labels[j]],
                "dimension_ratio": ratio,   # a / b (성분별)
                "source_group": group_key,
            })
    return masters, relations


def cluster_parts(parts):
    """
    파트들을 group_key 별로 묶고, 각 그룹에 대해 마스터/서브마스터 + 제약을 계산한다.

    - 인스턴스가 1개뿐인 그룹(예: Top) → unique_parts 로 분류(마스터 아님).
    - 인스턴스가 2개 이상 → evaluate_cluster_constraints 로 마스터/분기 처리.

    반환: {
        "unique_parts": [part...],           # 원본 파트 그대로 (전량 좌표 보존)
        "master_parts": [master...],
        "relations": [relation...],          # 서브마스터 간 관계
    }
    """
    groups = {}
    for p in parts:
        groups.setdefault(p["group_key"], []).append(p)

    unique_parts = []
    master_parts = []
    relations = []

    for key, members in groups.items():
        if len(members) == 1:
            unique_parts.append(_to_unique_part(members[0]))
            continue
        masters, rels = evaluate_cluster_constraints(key, members)
        master_parts.extend(masters)
        relations.extend(rels)

    print("[STEP] 클러스터링: unique {0}개, master {1}개, relations {2}개".format(
        len(unique_parts), len(master_parts), len(relations)))
    for m in master_parts:
        print("        └─ {0}: count={1} slots={2}".format(
            m["master_id"], m["instance_count"], len(m["slots"])))
    return {
        "unique_parts": unique_parts,
        "master_parts": master_parts,
        "relations": relations,
    }


def _to_unique_part(part):
    """단일 인스턴스 파트를 unique_parts 스키마로 정리한다."""
    return {
        "name": part["name"],
        "transform": part["transform"],
        "anchor_points": part["anchor_points"],
    }


# ===========================================================================
# [Task 8] 청사진 조립 + JSON 덤프 (파일 + 콘솔, tempfile fallback)
# ===========================================================================

def assemble_blueprint(entity, parts, clusters, topology):
    """
    모든 조각을 최종 시맨틱 청사진 dict 로 통합한다.

    global_constraints 에는 서브마스터 간 RATIO 관계를 올린다.
    """
    return {
        "schema_version": "1.0",
        "entity_type": entity["entity_type"],
        "instance_id": entity["instance_id"],
        "source_collection": entity["source_collection"],
        "metadata": entity["metadata"],
        "components": {
            "unique_parts": clusters["unique_parts"],
            "master_parts": clusters["master_parts"],
        },
        "topology": topology["edges"],
        "external_parents": topology["external_parents"],
        "global_constraints": clusters["relations"],
        "stats": {
            "total_mesh_parts": len(parts),
            "unique_count": len(clusters["unique_parts"]),
            "master_count": len(clusters["master_parts"]),
            "relation_count": len(clusters["relations"]),
        },
    }


def _resolve_output_path(entity):
    """
    출력 JSON 경로를 결정한다.

    우선순위:
        1) CONFIG["OUTPUT_DIR"] 지정 시 그 디렉토리
        2) .blend 저장돼 있으면 .blend 파일 옆
        3) 미저장 씬 → tempfile.gettempdir() fallback
    """
    filename = "{0}{1}{2}".format(
        entity["entity_type"],
        ("_" + entity["instance_id"]) if entity["instance_id"] else "",
        CONFIG["OUTPUT_SUFFIX"],
    )

    out_dir = CONFIG["OUTPUT_DIR"]
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)
        return os.path.join(out_dir, filename)

    # .blend 옆에 저장 시도
    blend_path = bpy.data.filepath if _HAS_BPY else ""
    if blend_path:
        return os.path.join(os.path.dirname(blend_path), filename)

    # 미저장 씬 → tempfile fallback
    tmp_dir = tempfile.gettempdir()
    print("   [info] 저장되지 않은 씬입니다. tempfile 경로로 출력합니다.")
    return os.path.join(tmp_dir, filename)


def dump_blueprint(blueprint):
    """
    청사진을 JSON 파일로 저장하고(콘솔 미리보기 옵션), 저장 경로를 반환한다.
    """
    entity = {
        "entity_type": blueprint["entity_type"],
        "instance_id": blueprint["instance_id"],
    }
    path = _resolve_output_path(entity)

    text = json.dumps(blueprint, indent=CONFIG["JSON_INDENT"], ensure_ascii=False)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)

    if CONFIG["PRINT_PREVIEW"]:
        print("\n" + "-" * 70)
        print(" SEMANTIC BLUEPRINT PREVIEW")
        print("-" * 70)
        print(text)

    return path


if __name__ == "__main__":
    main()