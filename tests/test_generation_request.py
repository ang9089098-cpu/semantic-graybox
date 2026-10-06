# -*- coding: utf-8 -*-
"""
Generation 경계 계층 unit test (AI 실제 실행 없음, 모델 로딩 없음).

실행:
    python -m unittest tests.test_generation_request -v
    (프로젝트 루트에서. cube3d/torch 불필요, bpy 불필요.)

검증 범위:
  1. GenerationRequest 생성 + JSON round-trip
  2. 같은 Master_Leg guide 4개가 request 1개로 합쳐지는지 (핵심 연구 의도)
  3. prompt builder 결과 (deterministic)
  4. guide ratio 정규화
  5. Cube3D CLI argument 생성 (bbox = 정규화 비율)
  6. adapter error handling (preflight 실패 / subprocess 실패 / OBJ 없음)
  7. mock output path 처리 (성공 경로)
"""

import json
import os
import sys
import unittest

# 프로젝트 루트를 import path 에 추가 (tests/ 의 부모)
HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(HERE)
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from generation.request import (
    GenerationRequest,
    normalize_ratio,
    requests_from_blueprint,
)
from generation.prompt_builder import build_prompt
from generation.generator_adapters.cube3d_adapter import Cube3DAdapter, Cube3DConfig
from generation.generator_adapters.base import GenerationResult


# extractor 가 만드는 것과 동일한 형태의 샘플 blueprint (Desk_01, 다리 4개).
SAMPLE_BLUEPRINT = {
    "schema_version": "1.0",
    "entity_type": "Desk",
    "instance_id": "01",
    "source_collection": "Desk_01",
    "metadata": {"style": "rococo"},
    "components": {
        "unique_parts": [
            {
                "name": "Top",
                "transform": {"location": [0, 0, 1], "rotation_euler": [0, 0, 0],
                              "scale": [2, 1, 0.1]},
                "anchor_points": {"dimensions": [2.0, 1.0, 0.1]},
            }
        ],
        "master_parts": [
            {
                "master_id": "Master_Leg",
                "source_group": "Leg",
                "instance_count": 4,
                "representative_dimensions": [0.08, 0.08, 0.70],
                "slots": [
                    {"name": "Leg_FL", "transform": {"location": [-0.9, -0.4, 0.35],
                     "rotation_euler": [0, 0, 0], "scale": [0.08, 0.08, 0.70]},
                     "direction": {}},
                    {"name": "Leg_FR", "transform": {"location": [0.9, -0.4, 0.35],
                     "rotation_euler": [0, 0, 0], "scale": [0.08, 0.08, 0.70]},
                     "direction": {}},
                    {"name": "Leg_BL", "transform": {"location": [-0.9, 0.4, 0.35],
                     "rotation_euler": [0, 0, 0], "scale": [0.08, 0.08, 0.70]},
                     "direction": {}},
                    {"name": "Leg_BR", "transform": {"location": [0.9, 0.4, 0.35],
                     "rotation_euler": [0, 0, 0], "scale": [0.08, 0.08, 0.70]},
                     "direction": {}},
                ],
                "constraints": [{"type": "EQUAL_DIMENSION"}],
            }
        ],
    },
    "topology": [],
}


def _fake_config(tmpdir):
    """실제 파일이 있는 것처럼 preflight 를 통과시키기 위한 config 헬퍼는
    테스트별로 monkeypatch 하므로, 여기서는 경로만 채운 config 반환."""
    return Cube3DConfig(
        python_exe=os.path.join(tmpdir, "python.exe"),
        repo_dir=tmpdir,
        gpt_ckpt=os.path.join(tmpdir, "shape_gpt.safetensors"),
        shape_ckpt=os.path.join(tmpdir, "shape_tokenizer.safetensors"),
        output_dir=os.path.join(tmpdir, "out"),
        fast_inference=False,
    )


class TestGenerationRequest(unittest.TestCase):
    def test_request_json_roundtrip(self):
        req = GenerationRequest(
            master_id="Master_Leg",
            semantic_type="furniture leg",
            parent_context="desk",
            style_prompt="rococo",
            guide_dimensions=(0.08, 0.08, 0.70),
            guide_ratio=(1.0, 1.0, 8.75),
            source_object_names=["Leg_FL", "Leg_FR"],
            instance_count=2,
        )
        d = req.to_dict()
        text = json.dumps(d)  # 직렬화 가능해야 함
        back = GenerationRequest.from_dict(json.loads(text))
        self.assertEqual(back.master_id, "Master_Leg")
        self.assertEqual(back.guide_ratio, (1.0, 1.0, 8.75))
        self.assertEqual(back.instance_count, 2)

    def test_master_leg_merges_into_single_request(self):
        """다리 4개 → request 1개, instance_count=4, source 4개 (핵심 규칙)."""
        reqs = requests_from_blueprint(SAMPLE_BLUEPRINT)
        leg = [r for r in reqs if r.master_id == "Master_Leg"]
        self.assertEqual(len(leg), 1, "Master_Leg 는 request 1개로 합쳐져야 함")
        leg = leg[0]
        self.assertEqual(leg.instance_count, 4)
        self.assertEqual(sorted(leg.source_object_names),
                         ["Leg_BL", "Leg_BR", "Leg_FL", "Leg_FR"])
        self.assertEqual(leg.semantic_type, "furniture leg")
        self.assertEqual(leg.parent_context, "desk")
        self.assertEqual(leg.style_prompt, "rococo")

    def test_unique_part_becomes_single_instance_request(self):
        reqs = requests_from_blueprint(SAMPLE_BLUEPRINT)
        top = [r for r in reqs if r.master_id == "Top"]
        self.assertEqual(len(top), 1)
        self.assertEqual(top[0].instance_count, 1)


class TestPromptBuilder(unittest.TestCase):
    def test_full_prompt(self):
        req = GenerationRequest(
            master_id="Master_Leg", semantic_type="furniture leg",
            parent_context="desk", style_prompt="rococo",
            guide_dimensions=(0.08, 0.08, 0.70), guide_ratio=(1.0, 1.0, 8.75),
        )
        self.assertEqual(build_prompt(req), "A rococo carved furniture leg for a desk")

    def test_prompt_without_style(self):
        req = GenerationRequest(
            master_id="Master_Leg", semantic_type="furniture leg",
            parent_context="desk", style_prompt=None,
            guide_dimensions=(0.08, 0.08, 0.70), guide_ratio=(1.0, 1.0, 8.75),
        )
        self.assertEqual(build_prompt(req), "A furniture leg for a desk")

    def test_prompt_without_parent(self):
        req = GenerationRequest(
            master_id="X", semantic_type="apple",
            parent_context=None, style_prompt=None,
            guide_dimensions=(1, 1, 1), guide_ratio=(1, 1, 1),
        )
        # 모음 시작 → "An apple"
        self.assertEqual(build_prompt(req), "An apple")

    def test_prompt_deterministic(self):
        req = GenerationRequest(
            master_id="Master_Leg", semantic_type="furniture leg",
            parent_context="desk", style_prompt="rococo",
            guide_dimensions=(0.08, 0.08, 0.70), guide_ratio=(1.0, 1.0, 8.75),
        )
        self.assertEqual(build_prompt(req), build_prompt(req))


class TestGuideRatio(unittest.TestCase):
    def test_normalize_ratio(self):
        self.assertEqual(normalize_ratio((0.08, 0.08, 0.70)), (1.0, 1.0, 8.75))

    def test_normalize_ratio_zero_component(self):
        r = normalize_ratio((0.0, 0.5, 1.0))
        self.assertEqual(r[0], 0.0)
        self.assertEqual(r[1], 1.0)
        self.assertEqual(r[2], 2.0)

    def test_normalize_ratio_all_zero(self):
        self.assertEqual(normalize_ratio((0.0, 0.0, 0.0)), (1.0, 1.0, 1.0))


class TestCube3DCliArgs(unittest.TestCase):
    def setUp(self):
        self.req = GenerationRequest(
            master_id="Master_Leg", semantic_type="furniture leg",
            parent_context="desk", style_prompt="rococo",
            guide_dimensions=(0.08, 0.08, 0.70), guide_ratio=(1.0, 1.0, 8.75),
            source_object_names=["Leg_FL"], instance_count=4,
        )
        self.cfg = _fake_config("/tmp/cube")

    def test_cli_args_contain_required_flags(self):
        adapter = Cube3DAdapter(self.cfg)
        args, meta = adapter.build_cli_args(self.req)
        self.assertIn("-m", args)
        self.assertIn("cube3d.generate", args)
        self.assertIn("--gpt-ckpt-path", args)
        self.assertIn("--shape-ckpt-path", args)
        self.assertIn("--prompt", args)
        # prompt 값이 rule-based 결과와 일치
        pi = args.index("--prompt")
        self.assertEqual(args[pi + 1], "A rococo carved furniture leg for a desk")

    def test_cli_args_bbox_is_normalized_ratio(self):
        adapter = Cube3DAdapter(self.cfg)
        args, meta = adapter.build_cli_args(self.req)
        self.assertIn("--bounding-box-xyz", args)
        bi = args.index("--bounding-box-xyz")
        self.assertEqual(args[bi + 1:bi + 4], ["1.0", "1.0", "8.75"])
        # diagnostics 에 원본/비율/전달 bbox 가 모두 기록됨
        self.assertEqual(meta["guide_dimensions"], [0.08, 0.08, 0.70])
        self.assertEqual(meta["guide_ratio"], [1.0, 1.0, 8.75])
        self.assertEqual(meta["passed_bounding_box"], [1.0, 1.0, 8.75])

    def test_no_fast_inference_flag_by_default(self):
        adapter = Cube3DAdapter(self.cfg)
        args, _ = adapter.build_cli_args(self.req)
        self.assertNotIn("--fast-inference", args)

    def test_fast_inference_flag_when_enabled(self):
        cfg = _fake_config("/tmp/cube")
        cfg.fast_inference = True
        adapter = Cube3DAdapter(cfg)
        args, _ = adapter.build_cli_args(self.req)
        self.assertIn("--fast-inference", args)

    def test_bbox_omitted_when_disabled(self):
        cfg = _fake_config("/tmp/cube")
        cfg.use_bounding_box = False
        adapter = Cube3DAdapter(cfg)
        args, meta = adapter.build_cli_args(self.req)
        self.assertNotIn("--bounding-box-xyz", args)
        self.assertIsNone(meta["passed_bounding_box"])


class TestCube3DErrorHandling(unittest.TestCase):
    def setUp(self):
        self.req = GenerationRequest(
            master_id="Master_Leg", semantic_type="furniture leg",
            parent_context="desk", style_prompt="rococo",
            guide_dimensions=(0.08, 0.08, 0.70), guide_ratio=(1.0, 1.0, 8.75),
        )

    def test_preflight_fails_when_venv_missing(self):
        cfg = _fake_config("/nonexistent_dir_xyz")
        adapter = Cube3DAdapter(cfg)
        result = adapter.generate(self.req)  # subprocess 까지 안 감
        self.assertFalse(result.success)
        self.assertIn("[CUBE3D_ERROR]", result.error)
        self.assertIn("Master_Leg", result.error)

    def test_classify_cuda_oom(self):
        reason = Cube3DAdapter.classify_failure(1, "RuntimeError: CUDA out of memory")
        self.assertIn("VRAM", reason)

    def test_classify_module_not_found(self):
        reason = Cube3DAdapter.classify_failure(1, "ModuleNotFoundError: No module named 'cube3d'")
        self.assertIn("not installed", reason)

    def test_classify_success(self):
        self.assertIsNone(Cube3DAdapter.classify_failure(0, ""))

    def test_subprocess_failure_returns_error_result(self):
        """preflight 통과(파일 존재)시키고, runner 를 실패로 주입."""
        import tempfile
        tmp = tempfile.mkdtemp()
        # preflight 통과용 더미 파일 생성
        for fn in ("python.exe", "shape_gpt.safetensors", "shape_tokenizer.safetensors"):
            open(os.path.join(tmp, fn), "w").close()
        cfg = _fake_config(tmp)
        cfg.python_exe = os.path.join(tmp, "python.exe")
        cfg.gpt_ckpt = os.path.join(tmp, "shape_gpt.safetensors")
        cfg.shape_ckpt = os.path.join(tmp, "shape_tokenizer.safetensors")
        adapter = Cube3DAdapter(cfg)

        class FakeProc:
            returncode = 1
            stdout = ""
            stderr = "RuntimeError: CUDA out of memory"

        result = adapter.generate(self.req, _runner=lambda a, c, t: FakeProc())
        self.assertFalse(result.success)
        self.assertIn("VRAM", result.error)

    def test_success_returns_output_path(self):
        """runner 성공 + OBJ 파일 존재 → success + output_path (mock output)."""
        import tempfile
        tmp = tempfile.mkdtemp()
        for fn in ("python.exe", "shape_gpt.safetensors", "shape_tokenizer.safetensors"):
            open(os.path.join(tmp, fn), "w").close()
        cfg = _fake_config(tmp)
        cfg.python_exe = os.path.join(tmp, "python.exe")
        cfg.gpt_ckpt = os.path.join(tmp, "shape_gpt.safetensors")
        cfg.shape_ckpt = os.path.join(tmp, "shape_tokenizer.safetensors")
        adapter = Cube3DAdapter(cfg)

        out_obj = adapter.expected_output_path()

        class FakeProc:
            returncode = 0
            stdout = "done"
            stderr = ""

        def runner(args, cwd, timeout):
            # 생성기가 OBJ 를 만든 것처럼 mock 파일 생성
            os.makedirs(cfg.output_dir, exist_ok=True)
            open(out_obj, "w").close()
            return FakeProc()

        result = adapter.generate(self.req, _runner=runner)
        self.assertTrue(result.success, result.error)
        self.assertEqual(result.output_path, out_obj)
        self.assertEqual(result.diagnostics["guide_ratio"], [1.0, 1.0, 8.75])

    def test_success_but_missing_obj_is_failure(self):
        import tempfile
        tmp = tempfile.mkdtemp()
        for fn in ("python.exe", "shape_gpt.safetensors", "shape_tokenizer.safetensors"):
            open(os.path.join(tmp, fn), "w").close()
        cfg = _fake_config(tmp)
        cfg.python_exe = os.path.join(tmp, "python.exe")
        cfg.gpt_ckpt = os.path.join(tmp, "shape_gpt.safetensors")
        cfg.shape_ckpt = os.path.join(tmp, "shape_tokenizer.safetensors")
        adapter = Cube3DAdapter(cfg)

        class FakeProc:
            returncode = 0
            stdout = "done"
            stderr = ""

        # OBJ 를 만들지 않는 runner
        result = adapter.generate(self.req, _runner=lambda a, c, t: FakeProc())
        self.assertFalse(result.success)
        self.assertIn("output OBJ not found", result.error)


if __name__ == "__main__":
    unittest.main(verbosity=2)