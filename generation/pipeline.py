# -*- coding: utf-8 -*-
"""
Generation Orchestration
=========================

Blender UI(Operator) 와 CLI 가 공유하는 **얇은 orchestration 계층**.
기존 함수들을 그대로 재사용하고, 여기서 새 로직을 만들지 않는다.

흐름 (요청 사양 4번 그대로):
    1. Target Collection 확인
    2. Semantic Graybox extractor 실행  (semantic_graybox_extractor.*)
    3. master/group 정보 추출          (cluster_parts / assemble_blueprint)
    4. GenerationRequest 생성          (generation.request.requests_from_blueprint)
    5. Style Prompt 적용               (request.style_prompt 에 주입 — 중립 필드)
    6. prompt_builder 실행             (adapter 내부에서 build_prompt 호출)
    7. Cube3D adapter 호출             (generation.generator_adapters.cube3d_adapter)
    8. 생성 OBJ path 수신
    9. Blender import                  (generation.blender_import.place_master_instances)
   10. 동일 master guide 에 instance 배치

이 모듈은 bpy 를 방어적으로 import 한다. extractor 의 blueprint 생성 함수들은
bpy 에 의존하므로, blueprint 생성은 Blender 안에서만 가능하다.
UI 코드는 Cube3D 전용 prompt 문자열을 만들지 않는다(요청 7번). style 만 넘긴다.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field, replace
import copy
import re
import uuid
from typing import Optional

# 프로젝트 루트를 path 에 넣어 production extractor 를 import 가능하게 한다.
_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_THIS_DIR)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from generation.request import requests_from_blueprint, GenerationRequest
from generation.generator_adapters.cube3d_adapter import Cube3DAdapter, Cube3DConfig
from generation.generator_adapters.base import GenerationResult
from generation.semantic_review import SemanticReview


@dataclass
class PipelineOutcome:
    """orchestration 결과. UI 가 이 값으로 report 메시지를 만든다."""
    success: bool
    message: str
    master_id: Optional[str] = None
    output_path: Optional[str] = None
    instance_count: int = 0
    final_prompt: Optional[str] = None
    request: Optional[GenerationRequest] = None
    result: Optional[GenerationResult] = None


def build_blueprint_from_collection(collection):
    """
    기존 production extractor 함수들을 그대로 호출해 blueprint dict 를 만든다.
    (duplicate logic 금지 — extractor 의 파이프라인 함수 재사용.)

    Blender 안에서만 동작(bpy 필요). collection 은 bpy Collection.
    """
    import semantic_graybox_extractor as ext  # bpy 의존 → 지연 import

    entity = ext.parse_entity_context(collection)
    parts = ext.collect_parts(collection)
    if not parts:
        return None, entity  # 호출부에서 "MESH 없음" 처리
    topology = ext.build_topology(parts)
    clusters = ext.cluster_parts(parts)
    blueprint = ext.assemble_blueprint(entity, parts, clusters, topology)
    return blueprint, entity


def _find_master(blueprint: dict, master_id: Optional[str]):
    """
    blueprint 에서 배치할 master dict 를 고른다.
    master_id 지정 시 그것, 아니면 첫 master_part.
    """
    masters = blueprint.get("components", {}).get("master_parts", [])
    if not masters:
        return None
    if master_id:
        for m in masters:
            if m.get("master_id") == master_id:
                return m
    return masters[0]


def _apply_style(requests, style_prompt: Optional[str]):
    """
    UI 에서 입력한 style 을 각 request 의 **중립 필드 style_prompt** 에 주입한다.
    (Cube3D 전용 최종 prompt 문자열을 만들지 않는다 — prompt_builder 가 담당.)
    빈 문자열/None 이면 기존 값 유지.
    """
    s = (style_prompt or "").strip()
    if not s:
        return requests
    for r in requests:
        r.style_prompt = s
    return requests


def run_generation(collection,
                   style_prompt: Optional[str] = None,
                   generator: str = "cube3d",
                   master_id: Optional[str] = None,
                   config: Optional[Cube3DConfig] = None,
                   do_import: bool = True,
                   base_dir: Optional[str] = None) -> PipelineOutcome:
    """
    전체 orchestration. UI Operator 는 이 함수만 호출한다.

    파라미터
    --------
    collection   : 대상 bpy Collection
    style_prompt : UI 입력값 → GenerationRequest.style_prompt (중립 필드)
    generator    : 현재 "cube3d" 만 지원
    master_id    : 배치할 master (None 이면 첫 master_part)
    config       : Cube3DConfig (None 이면 from_env 로 관례 경로 사용)
    do_import    : True 면 생성 OBJ 를 Blender 에 import + 인스턴싱
    base_dir     : from_env 기준 경로 (None 이면 프로젝트 루트)

    반환: PipelineOutcome (성공/실패 + 메시지 + 진단)
    """
    if generator != "cube3d":
        return PipelineOutcome(False, "Unsupported generator: {0}".format(generator))

    # (1) Target Collection 확인
    if collection is None:
        return PipelineOutcome(False, "Target Collection is not set.")

    # (2)(3) extractor 실행 → blueprint
    blueprint, _entity = build_blueprint_from_collection(collection)
    if blueprint is None:
        return PipelineOutcome(
            False,
            "No MESH parts found in collection '{0}'.".format(getattr(collection, "name", "?")),
        )

    # (4) GenerationRequest 생성
    requests = requests_from_blueprint(blueprint)
    if not requests:
        return PipelineOutcome(False, "No generation requests could be built.")

    # (5) Style Prompt 적용 (중립 필드)
    _apply_style(requests, style_prompt)

    # 배치 대상 master 선택
    master = _find_master(blueprint, master_id)
    if master is None:
        return PipelineOutcome(
            False, "No master_part to generate (need repeated parts, e.g. Master_Leg).")
    target_master_id = master.get("master_id")

    # 이 master 에 대응하는 request 찾기
    req = next((r for r in requests if r.master_id == target_master_id), None)
    if req is None:
        return PipelineOutcome(False, "No request matched master '{0}'.".format(target_master_id))

    # (6)(7) adapter 호출 (adapter 내부에서 prompt_builder 실행)
    if config is None:
        if base_dir is None:
            base_dir = _PROJECT_ROOT
        config = Cube3DConfig.from_env(base_dir=base_dir)
    adapter = Cube3DAdapter(config)
    final_prompt = adapter._build_prompt(req)   # 진단/표시용 (같은 함수를 adapter 가 사용)

    result = adapter.generate(req)
    if not result.success:
        return PipelineOutcome(
            False,
            result.error or "Generation failed.",
            master_id=target_master_id,
            final_prompt=final_prompt,
            request=req,
            result=result,
        )

    # (8) OBJ path 수신
    obj_path = result.output_path

    # (9)(10) Blender import + 인스턴싱 (guide 유지, 별도 Generated 컬렉션)
    placed = 0
    if do_import:
        try:
            from generation.blender_import import place_master_instances
            instances = place_master_instances(obj_path, master, "Generated")
            placed = len(instances)
        except Exception as exc:  # noqa: BLE001
            return PipelineOutcome(
                False,
                "Import failed: {0}".format(exc),
                master_id=target_master_id,
                output_path=obj_path,
                final_prompt=final_prompt,
                request=req,
                result=result,
            )

    return PipelineOutcome(
        True,
        "Generation completed: {0}".format(target_master_id),
        master_id=target_master_id,
        output_path=obj_path,
        instance_count=placed,
        final_prompt=final_prompt,
        request=req,
        result=result,
    )


@dataclass
class GenerationUnitResult:
    unit_id: str
    kind: str
    request: GenerationRequest
    placement: dict
    status: str = "PENDING"
    success: bool = False
    message: str = ""
    output_path: Optional[str] = None
    instance_count: int = 0
    result: Optional[GenerationResult] = None
    review: SemanticReview = field(init=False)

    def __post_init__(self):
        self.review = SemanticReview(self.unit_id)


@dataclass
class GenerationBatchResult:
    run_id: str
    results: list = field(default_factory=list)

    @property
    def total(self):
        return len(self.results)

    @property
    def completed(self):
        return sum(u.status in ("DONE", "KEPT") for u in self.results)

    @property
    def failed(self):
        return sum(u.status == "ERROR" for u in self.results)

    @property
    def finished(self):
        return self.completed + self.failed == self.total

    @property
    def success(self):
        return bool(self.total) and self.finished and not self.failed

    @property
    def message(self):
        return "Generation {0}: {1} / {2} completed, {3} failed".format(
            "Complete" if self.success else "Finished", self.completed, self.total, self.failed)


class GenerationQueue:
    """FIFO queue. Only generate() may run off-thread; finish() imports on the caller.

    Requests remain the execution plan. Placement consumes the original blueprint
    slots independently, including the single slot of every unique part.
    """
    def __init__(self, blueprint, style_prompt=None, generator="cube3d", config=None,
                 do_import=True, base_dir=None, adapter_factory=None, placer=None):
        if generator != "cube3d":
            raise ValueError("Unsupported generator: " + generator)
        self.config = config or Cube3DConfig.from_env(base_dir or _PROJECT_ROOT)
        self.do_import = do_import
        self.adapter_factory = adapter_factory or Cube3DAdapter
        self.placer = placer
        self.batch = GenerationBatchResult(uuid.uuid4().hex)
        requests = _apply_style(requests_from_blueprint(blueprint), style_prompt)
        placements = {}
        for master in blueprint.get("components", {}).get("master_parts", []):
            placements[master["master_id"]] = copy.deepcopy(master)
        for part in blueprint.get("components", {}).get("unique_parts", []):
            placements[part["name"]] = {"master_id": part["name"], "slots": [copy.deepcopy(part)]}
        ids = [r.master_id for r in requests]
        if len(ids) != len(set(ids)):
            raise ValueError("Generation Unit IDs must be unique.")
        if not requests:
            raise ValueError("No generation requests could be built.")
        master_ids = {m["master_id"] for m in blueprint.get("components", {}).get("master_parts", [])}
        for req in requests:
            self.batch.results.append(GenerationUnitResult(
                req.master_id, "MASTER" if req.master_id in master_ids else "UNIQUE",
                req, placements[req.master_id]))
        entity = re.sub(r"[^A-Za-z0-9_-]+", "_", blueprint.get("entity_type") or "Entity")[:64] or "Entity"
        self.output_root = os.path.join(self.config.output_dir, entity, self.batch.run_id)
        self.entity = blueprint.get("entity_type") or "Entity"

    def begin_next(self):
        if any(u.status == "GENERATING" for u in self.batch.results):
            raise RuntimeError("A Generation Unit is already running.")
        unit = next((u for u in self.batch.results if u.status == "PENDING"), None)
        if unit:
            unit.status = "GENERATING"
        return unit

    def generate(self, unit):
        """External generator only: no Blender objects or state are accessed here."""
        index = self.batch.results.index(unit)
        slug = re.sub(r"[^A-Za-z0-9_-]+", "_", unit.unit_id)[:64] or "Unit"
        cfg = replace(self.config, output_dir=os.path.join(self.output_root, f"{index + 1:03d}_{slug}"))
        try:
            return self.adapter_factory(cfg).generate(unit.request)
        except Exception as exc:
            return GenerationResult(False, unit.unit_id, error=str(exc))

    def finish(self, unit, result):
        if unit.status != "GENERATING":
            raise RuntimeError("Only a running unit can finish.")
        unit.result = result
        unit.output_path = result.output_path
        if not result.success or not result.output_path or not os.path.isfile(result.output_path):
            unit.status = "ERROR"
            unit.message = result.error or "Generation returned no output OBJ."
            return unit
        try:
            if self.do_import:
                placer = self.placer
                if placer is None:
                    from generation.blender_import import place_master_instances
                    placer = place_master_instances
                objects = placer(result.output_path, unit.placement, "Generated")
                unit.instance_count = len(objects)
                for obj in objects:
                    obj["semantic_graybox_generated"] = True
                    obj["generation_unit_id"] = unit.unit_id
                    obj["source_entity"] = self.entity
                    obj["semantic_graybox_run"] = self.batch.run_id
                    obj["semantic_graybox_kept"] = False
            unit.success = True
            unit.status = "DONE"
            unit.message = "Generation completed: " + unit.unit_id
        except Exception as exc:
            unit.status = "ERROR"
            unit.message = "Import failed: " + str(exc)
        return unit


def run_generation_batch(collection=None, style_prompt=None, generator="cube3d",
                         config=None, do_import=True, base_dir=None, *, blueprint=None,
                         adapter_factory=None, placer=None, on_progress=None):
    """Synchronous CLI/test entry point; UI uses the same queue with a worker.

    A failed unit never rolls back successful units. Original single-master
    run_generation() and semantic_graybox.generate remain unchanged.
    """
    if blueprint is None:
        if collection is None:
            raise ValueError("Target Collection is not set.")
        blueprint, _ = build_blueprint_from_collection(collection)
        if blueprint is None:
            raise ValueError("No MESH parts found in Target Collection.")
    queue = GenerationQueue(blueprint, style_prompt, generator, config, do_import,
                            base_dir, adapter_factory, placer)
    while True:
        unit = queue.begin_next()
        if unit is None:
            break
        if on_progress:
            on_progress(queue.batch, unit)
        queue.finish(unit, queue.generate(unit))
        if on_progress:
            on_progress(queue.batch, unit)
    return queue.batch