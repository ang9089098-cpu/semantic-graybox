# -*- coding: utf-8 -*-
"""
Prompt Builder
==============

:class:`GenerationRequest` → Cube3D 용 text prompt.

원칙
----
- **deterministic / rule-based**. LLM 을 부르지 않는다. (같은 입력 → 같은 출력)
- 같은 master 는 항상 같은 prompt → 생성 결과 일관성 확보.
- guide 비율은 여기서 문장에 억지로 넣지 않는다. (비율은 adapter 의 bbox conditioning 으로 전달)

규칙
----
    semantic_type = "furniture leg"
    parent_context = "desk"
    style = "rococo"
        → "A rococo carved furniture leg for a desk"

    style 없으면 "carved" 수식/스타일 토큰을 생략:
        → "A furniture leg for a desk"

    parent_context 없으면 "for a ..." 절 생략.
"""

from __future__ import annotations

from .request import GenerationRequest


def _article(word: str) -> str:
    """단어 첫 소리에 따라 a/an 선택 (간단한 모음 규칙)."""
    return "an" if word[:1].lower() in "aeiou" else "a"


def build_prompt(request: GenerationRequest) -> str:
    """
    GenerationRequest 를 단순 규칙으로 자연어 prompt 로 변환한다.

    형식: "A [style] [carved] [semantic_type] for a [parent_context]"
      - style 이 있으면 style + "carved" 수식을 붙인다 (예시 사양: rococo carved).
      - parent_context 가 있으면 "for a/an <context>" 절을 붙인다.
    """
    semantic = (request.semantic_type or "object").strip()
    style = (request.style_prompt or "").strip()
    parent = (request.parent_context or "").strip()

    head = _article(style if style else semantic).capitalize()

    parts = [head]
    if style:
        parts.append(style)
        parts.append("carved")
    parts.append(semantic)

    prompt = " ".join(parts)

    if parent:
        prompt = "{0} for {1} {2}".format(prompt, _article(parent), parent)

    return prompt