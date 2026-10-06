# -*- coding: utf-8 -*-
"""
GenerationRequest
=================

extractor 의 semantic blueprint 를 **생성기 중립(neutral)** 데이터로 변환한 경계 타입.

핵심 규칙 (Semantic Graybox 연구 의도 반영)
------------------------------------------
- 같은 master(예: Master_Leg) 를 공유하는 부품들은 **request 1개** 로 합쳐진다.
  → 생성기는 다리를 1번만 만들고, Blender 에서 4개 인스턴스로 배치한다.
- guide dimensions 는 **hard container 가 아니라** 상대 형태/비율 hint 이다.
  따라서 원본 dimension 과 정규화된 비율(guide_ratio) 을 함께 보존한다.
- 무엇을 만들지(semantic)와 어디에 놓을지(anchor/transform)를 분리한다.
  → transform/anchor 는 slots 에 남고, request 는 "무엇을/어떤 비율로" 만 담는다.

이 dataclass 는 plain Python 값만 담아 JSON 직렬화가 가능하다. (Blender 객체 금지.)
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Optional


# ---------------------------------------------------------------------------
# 비율 계산 헬퍼 — bpy/numpy 없이 순수 파이썬으로만 동작한다.
# ---------------------------------------------------------------------------
def normalize_ratio(dimensions, precision: int = 6):
    """
    guide dimensions 를 "최소 성분 = 1.0" 기준의 상대 비율로 정규화한다.

        (0.08, 0.08, 0.70) -> (1.0, 1.0, 8.75)

    - 0/음수 성분은 절대값 + 하한(1e-9)으로 방어한다.
    - 모든 성분이 0 에 가까우면 (1,1,1) 로 fallback.
    """
    dims = [abs(float(d)) for d in dimensions]
    positive = [d for d in dims if d > 1e-9]
    if not positive:
        return (1.0, 1.0, 1.0)
    base = min(positive)
    ratio = tuple(round(d / base, precision) if d > 1e-9 else 0.0 for d in dims)
    return ratio


@dataclass
class GenerationRequest:
    """
    생성기 중립 요청. Cube3D 전용 옵션은 여기에 넣지 않는다. (adapter 가 담당.)

    필드
    ----
    master_id            : 소스 master 식별자 (예: "Master_Leg")
    semantic_type        : 의미 역할 (예: "furniture leg")
    parent_context       : 상위 엔티티 문맥 (예: "desk"), 없으면 None
    style_prompt         : 스타일 힌트 (예: "rococo"), 없으면 None
    guide_dimensions     : 대표 guide 크기 (x, y, z) — 원본 절대값 보존
    guide_ratio          : guide_dimensions 를 정규화한 상대 비율
    source_object_names  : 이 request 로 합쳐진 원본 오브젝트 이름들
    instance_count       : 배치할 인스턴스 수 (= len(source_object_names) 기본)
    """

    master_id: str
    semantic_type: str
    parent_context: Optional[str]
    style_prompt: Optional[str]

    guide_dimensions: tuple  # (x, y, z)
    guide_ratio: tuple       # (x, y, z) normalized

    source_object_names: list = field(default_factory=list)
    instance_count: int = 1

    # -- 직렬화 ----------------------------------------------------------
    def to_dict(self) -> dict:
        """JSON 직렬화 가능한 dict 로 변환 (tuple → list)."""
        d = asdict(self)
        d["guide_dimensions"] = list(self.guide_dimensions)
        d["guide_ratio"] = list(self.guide_ratio)
        d["source_object_names"] = list(self.source_object_names)
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "GenerationRequest":
        return cls(
            master_id=d["master_id"],
            semantic_type=d["semantic_type"],
            parent_context=d.get("parent_context"),
            style_prompt=d.get("style_prompt"),
            guide_dimensions=tuple(d["guide_dimensions"]),
            guide_ratio=tuple(d["guide_ratio"]),
            source_object_names=list(d.get("source_object_names", [])),
            instance_count=int(d.get("instance_count", 1)),
        )


# ---------------------------------------------------------------------------
# semantic role 매핑 — group key/entity 이름을 사람이 읽는 semantic_type 으로.
# 미등록 키는 소문자 원문을 그대로 semantic_type 으로 사용한다 (deterministic fallback).
# ---------------------------------------------------------------------------
SEMANTIC_TYPE_MAP = {
    "Headboard": "headboard",
    "SideFrame": "side frame",
    "LeftSideFrame": "side frame",
    "RightSideFrame": "side frame",
    "Leg": "furniture leg",
    "Top": "table top",
    "Seat": "chair seat",
    "Back": "chair backrest",
    "Arm": "armrest",
    "Drawer": "drawer",
    "Shelf": "shelf board",
    "Panel": "panel",
}

ENTITY_CONTEXT_MAP = {
    "Bed": "bed",
    "Desk": "desk",
    "Table": "table",
    "Chair": "chair",
    "Cabinet": "cabinet",
    "Shelf": "shelving unit",
}


def _semantic_type_for(source_group: str, master_id: str) -> str:
    if source_group and source_group in SEMANTIC_TYPE_MAP:
        return SEMANTIC_TYPE_MAP[source_group]
    if source_group:
        return source_group.replace("_", " ").lower()
    # master_id "Master_Leg" -> "leg"
    tail = master_id.split("_", 1)[-1] if "_" in master_id else master_id
    return tail.replace("_", " ").lower()


def _parent_context_for(entity_type: Optional[str]) -> Optional[str]:
    if not entity_type:
        return None
    return ENTITY_CONTEXT_MAP.get(entity_type, entity_type.replace("_", " ").lower())


def requests_from_blueprint(blueprint: dict, precision: int = 6):
    """
    extractor blueprint dict → :class:`GenerationRequest` 리스트.

    - `components.master_parts` 의 각 master 를 request 1개로 변환한다.
      (같은 master 의 여러 slot 은 이미 1개 master 로 합쳐져 있으므로 request 도 1개.)
    - `components.unique_parts` 는 인스턴스 1개짜리 request 로 변환한다.
    - style_prompt 는 blueprint.metadata.style 에서 가져온다(있으면).

    이 함수는 extractor 를 import 하지 않고, extractor 가 이미 만든 dict 만 소비한다.
    """
    style = None
    metadata = blueprint.get("metadata") or {}
    if isinstance(metadata, dict):
        style = metadata.get("style")

    entity_type = blueprint.get("entity_type")
    parent_ctx = _parent_context_for(entity_type)

    requests = []

    # --- master parts (반복 부품 → 1 request) ---
    for master in blueprint.get("components", {}).get("master_parts", []):
        source_group = master.get("source_group", "")
        master_id = master.get("master_id", source_group or "Master")
        rep_dims = tuple(master.get("representative_dimensions", (0.0, 0.0, 0.0)))
        slots = master.get("slots", [])
        names = [s.get("name") for s in slots if s.get("name")]
        requests.append(
            GenerationRequest(
                master_id=master_id,
                semantic_type=_semantic_type_for(source_group, master_id),
                parent_context=parent_ctx,
                style_prompt=style,
                guide_dimensions=rep_dims,
                guide_ratio=normalize_ratio(rep_dims, precision),
                source_object_names=names,
                instance_count=master.get("instance_count", len(names) or 1),
            )
        )

    # --- unique parts (단일 부품 → 1 request, 1 instance) ---
    for part in blueprint.get("components", {}).get("unique_parts", []):
        name = part.get("name", "Part")
        # unique part 는 group key 정보가 없으므로 이름에서 유추
        group_guess = name.split("_", 1)[0].split(".")[0]
        dims = tuple(part.get("anchor_points", {}).get("dimensions", (0.0, 0.0, 0.0)))
        requests.append(
            GenerationRequest(
                master_id=name,
                semantic_type=_semantic_type_for(group_guess, name),
                parent_context=parent_ctx,
                style_prompt=style,
                guide_dimensions=dims,
                guide_ratio=normalize_ratio(dims, precision),
                source_object_names=[name],
                instance_count=1,
            )
        )

    return requests