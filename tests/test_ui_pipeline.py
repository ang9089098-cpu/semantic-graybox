# -*- coding: utf-8 -*-
"""
UI orchestration layer unit test (bpy 불필요, Cube3D 실제 실행 없음).

실행:
    python -m unittest tests.test_ui_pipeline -v

검증:
  1. style prompt 값이 GenerationRequest.style_prompt 로 전달되는지 (중립 필드)
  2. prompt_builder 가 예상 문자열 생성하는지 (UI 입력 style 반영)
  3. Collection semantic context(parent_context) 전달 확인
  4. pipeline validation logic (collection None / master 없음 / unsupported generator)
  5. prompt empty 처리 (_apply_style 가 빈 값이면 기존 유지)
"""

import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(HERE)
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from generation.request import requests_from_blueprint
from generation.prompt_builder import build_prompt
from generation.pipeline import _apply_style, _find_master, run_generation, PipelineOutcome


SAMPLE_BLUEPRINT = {
    "entity_type": "Desk",
    "instance_id": "01",
    "metadata": {},   # UI 가 style 을 주입하므로 metadata.style 은 비워둔다
    "components": {
        "unique_parts": [
            {"name": "Top", "transform": {}, "anchor_points": {"dimensions": [2.0, 1.0, 0.1]}}
        ],
        "master_parts": [
            {
                "master_id": "Master_Leg", "source_group": "Leg", "instance_count": 4,
                "representative_dimensions": [0.08, 0.08, 0.70],
                "slots": [
                    {"name": "Leg_FL", "transform": {}, "direction": {}},
                    {"name": "Leg_FR", "transform": {}, "direction": {}},
                    {"name": "Leg_BL", "transform": {}, "direction": {}},
                    {"name": "Leg_BR", "transform": {}, "direction": {}},
                ],
                "constraints": [],
            }
        ],
    },
    "topology": [],
}


class TestStyleInjection(unittest.TestCase):
    def test_ui_style_goes_to_style_prompt_field(self):
        reqs = requests_from_blueprint(SAMPLE_BLUEPRINT)
        # UI 입력 "Rococo" 주입
        _apply_style(reqs, "Rococo")
        leg = next(r for r in reqs if r.master_id == "Master_Leg")
        self.assertEqual(leg.style_prompt, "Rococo")

    def test_prompt_builder_reflects_ui_style(self):
        reqs = requests_from_blueprint(SAMPLE_BLUEPRINT)
        _apply_style(reqs, "rococo")
        leg = next(r for r in reqs if r.master_id == "Master_Leg")
        self.assertEqual(build_prompt(leg), "A rococo carved furniture leg for a desk")

    def test_collection_semantic_context(self):
        reqs = requests_from_blueprint(SAMPLE_BLUEPRINT)
        leg = next(r for r in reqs if r.master_id == "Master_Leg")
        # Desk collection → parent_context "desk", Leg → "furniture leg"
        self.assertEqual(leg.parent_context, "desk")
        self.assertEqual(leg.semantic_type, "furniture leg")

    def test_empty_style_keeps_existing(self):
        reqs = requests_from_blueprint(SAMPLE_BLUEPRINT)
        for r in reqs:
            r.style_prompt = "keepme"
        _apply_style(reqs, "   ")   # 공백 → 무시
        self.assertTrue(all(r.style_prompt == "keepme" for r in reqs))


class TestFindMaster(unittest.TestCase):
    def test_find_by_id(self):
        m = _find_master(SAMPLE_BLUEPRINT, "Master_Leg")
        self.assertIsNotNone(m)
        self.assertEqual(m["master_id"], "Master_Leg")

    def test_find_default_first(self):
        m = _find_master(SAMPLE_BLUEPRINT, None)
        self.assertEqual(m["master_id"], "Master_Leg")

    def test_no_masters(self):
        bp = {"components": {"master_parts": []}}
        self.assertIsNone(_find_master(bp, None))


class TestPipelineValidation(unittest.TestCase):
    def test_collection_none(self):
        outcome = run_generation(collection=None, style_prompt="rococo")
        self.assertFalse(outcome.success)
        self.assertIn("Target Collection", outcome.message)

    def test_unsupported_generator(self):
        outcome = run_generation(collection=object(), style_prompt="x", generator="nope")
        self.assertFalse(outcome.success)
        self.assertIn("Unsupported generator", outcome.message)


if __name__ == "__main__":
    unittest.main(verbosity=2)