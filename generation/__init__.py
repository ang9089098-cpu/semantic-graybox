# -*- coding: utf-8 -*-
"""
generation
==========

Semantic Graybox extractor 와 외부 3D 생성 백엔드(Cube3D 등) 사이의 **중립 경계** 계층.

설계 원칙
---------
- 이 패키지는 특정 생성기(Cube3D)에 종속되지 않는다. extractor 가 만든 blueprint 를
  중립적인 :class:`GenerationRequest` 로 변환하고, 교체 가능한 adapter 가 실제 생성기를 호출한다.
- production extractor(`semantic_graybox_extractor.py`)는 이 패키지를 import 하지 않는다.
  (단방향 의존성: generation → extractor blueprint dict 만 소비.)
- `bpy` 에 의존하지 않는다. Blender import 헬퍼(`blender_import.py`)만 bpy 를 방어적으로 사용한다.
"""

from .request import GenerationRequest, requests_from_blueprint
from .prompt_builder import build_prompt

__all__ = [
    "GenerationRequest",
    "requests_from_blueprint",
    "build_prompt",
]