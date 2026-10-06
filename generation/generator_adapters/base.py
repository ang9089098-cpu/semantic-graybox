# -*- coding: utf-8 -*-
"""
Adapter 공통 인터페이스 + 결과 타입.

generator 교체 용이성을 위해 모든 adapter 는 동일한 형태를 따른다:

    result = adapter.generate(request)
    result.success        # bool
    result.output_path    # 성공 시 OBJ 경로, 실패 시 None
    result.stdout / stderr
    result.error          # 사람이 읽는 실패 사유 (실패 시)

이 모듈은 bpy / torch / cube3d 에 의존하지 않는다.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from ..request import GenerationRequest


@dataclass
class GenerationResult:
    """생성 시도 결과 (성공/실패 공통)."""
    success: bool
    request_master_id: str
    output_path: Optional[str] = None
    stdout: str = ""
    stderr: str = ""
    error: Optional[str] = None          # 실패 사유 (사람이 읽는 요약)
    # 진단/재현용 메타: 원본 guide, 정규화 비율, 실제 백엔드에 전달된 bbox, CLI args
    diagnostics: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "success": self.success,
            "request_master_id": self.request_master_id,
            "output_path": self.output_path,
            "stdout": self.stdout,
            "stderr": self.stderr,
            "error": self.error,
            "diagnostics": self.diagnostics,
        }


class GeneratorAdapter:
    """모든 생성기 adapter 가 상속하는 최소 인터페이스."""

    name = "base"

    def generate(self, request: GenerationRequest) -> GenerationResult:  # pragma: no cover
        raise NotImplementedError