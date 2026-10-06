# -*- coding: utf-8 -*-
"""
generator_adapters
==================

교체 가능한 생성기 adapter 들. 각 adapter 는 중립 :class:`GenerationRequest` 를 받아
자신의 백엔드(Cube3D / Hunyuan / Trellis / CubePart 등)를 호출하고
:class:`GenerationResult` 를 반환한다.

현재 구현: cube3d_adapter (subprocess 기반 CLI adapter).
미래 확장: hunyuan_adapter, trellis_adapter, cubepart_adapter.
"""

from .base import GenerationResult, GeneratorAdapter

__all__ = ["GenerationResult", "GeneratorAdapter"]