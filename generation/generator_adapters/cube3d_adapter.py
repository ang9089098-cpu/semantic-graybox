# -*- coding: utf-8 -*-
"""
Cube3D Adapter (subprocess / CLI 기반)
=====================================

역할 (딱 이것만):
    GenerationRequest
      → Cube3D CLI 인자 생성
      → **외부 Python 프로세스** 실행 (별도 venv 의 python.exe)
      → 성공/실패 판정
      → 생성된 OBJ 경로 반환 (GenerationResult)

왜 subprocess 인가
------------------
- Blender 내장 Python 과 Cube3D(torch/CUDA) 환경을 **완전 분리**한다.
- dependency 충돌 방지, generator 교체 용이, crash isolation, 디버깅 용이.
- 이 파일은 torch/cube3d 를 절대 import 하지 않는다. (unit test 시 8GB 모델 로딩 X)

Cube3D v0.5 CLI 계약 (공식 repo 기준):
    python -m cube3d.generate
        --gpt-ckpt-path   <shape_gpt.safetensors>
        --shape-ckpt-path <shape_tokenizer.safetensors>
        --prompt          "<text>"
        [--bounding-box-xyz X Y Z]
        [--output-dir <dir>]
        [--fast-inference]         # 24GB+ VRAM 권장. 16GB 이하면 생략.
        [--resolution-base 8.0]
        [--config-path <yaml>]
    → OBJ 는 {output_dir}/output.obj 로 저장된다 (output_name 기본 "output").

Guide/BBox 정책 (연구 의도)
--------------------------
- guide 는 hard container 가 아니다. bbox conditioning 은 **상대 비율 hint** 로만 쓴다.
- 자동으로 극단 fitting/비균일 스케일을 하지 않는다.
- 진단을 위해 (원본 guide, 정규화 비율, 실제 전달 bbox) 를 모두 diagnostics 에 남긴다.
- bbox 전달은 옵션(use_bounding_box). 기본은 정규화 비율을 bbox 로 전달.
"""

from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from typing import Optional

from ..request import GenerationRequest
from .base import GenerationResult, GeneratorAdapter


@dataclass
class Cube3DConfig:
    """
    Cube3D 실행 환경 설정. (Blender 와 분리된 별도 venv/repo 경로)

    python_exe   : 별도 venv 의 python 실행 파일 (예: tools/cube/.venv/Scripts/python.exe)
    repo_dir     : cube repo 루트 (cwd 로 사용, `python -m cube3d.generate` 실행 위치)
    gpt_ckpt     : shape_gpt.safetensors 경로
    shape_ckpt   : shape_tokenizer.safetensors 경로
    output_dir   : OBJ 출력 폴더
    fast_inference : --fast-inference 사용 여부 (24GB+ VRAM 권장)
    resolution_base: 셰이프 디코더 해상도 (낮을수록 빠름/저품질)
    config_path  : None 이면 CLI 기본값(v0.5) 사용
    timeout_sec  : subprocess 타임아웃 (초)
    use_bounding_box : guide 비율을 --bounding-box-xyz 로 전달할지 여부
    """
    python_exe: str
    repo_dir: str
    gpt_ckpt: str
    shape_ckpt: str
    output_dir: str
    fast_inference: bool = False
    resolution_base: float = 8.0
    config_path: Optional[str] = None
    timeout_sec: int = 1800
    use_bounding_box: bool = True

    @classmethod
    def from_env(cls, base_dir: str) -> "Cube3DConfig":
        """
        환경변수/관례 경로로부터 config 를 구성한다. (README 관례: tools/cube)

        환경변수(선택):
            CUBE3D_PYTHON   : venv python 경로
            CUBE3D_REPO     : cube repo 경로
            CUBE3D_WEIGHTS  : model_weights 폴더
            CUBE3D_OUTPUT   : 출력 폴더
            CUBE3D_FAST     : "1" 이면 fast-inference
        base_dir 는 project_work 루트로, 관례 경로의 기준점.
        """
        repo = os.environ.get("CUBE3D_REPO", os.path.join(base_dir, "tools", "cube"))
        py = os.environ.get(
            "CUBE3D_PYTHON",
            os.path.join(repo, ".venv", "Scripts", "python.exe"),
        )
        weights = os.environ.get("CUBE3D_WEIGHTS", os.path.join(repo, "model_weights"))
        out = os.environ.get("CUBE3D_OUTPUT", os.path.join(base_dir, "Generated"))
        fast = os.environ.get("CUBE3D_FAST", "0") == "1"
        return cls(
            python_exe=py,
            repo_dir=repo,
            gpt_ckpt=os.path.join(weights, "shape_gpt.safetensors"),
            shape_ckpt=os.path.join(weights, "shape_tokenizer.safetensors"),
            output_dir=out,
            fast_inference=fast,
        )


class Cube3DAdapter(GeneratorAdapter):
    """Cube3D v0.5 를 subprocess CLI 로 구동하는 adapter."""

    name = "cube3d"

    def __init__(self, config: Cube3DConfig, prompt_builder=None):
        self.config = config
        # prompt_builder 주입 (기본은 rule-based build_prompt)
        if prompt_builder is None:
            from ..prompt_builder import build_prompt
            prompt_builder = build_prompt
        self._build_prompt = prompt_builder

    # ------------------------------------------------------------------
    # 1) 순수 로직: CLI 인자 생성 (subprocess 없이 단위 테스트 가능)
    # ------------------------------------------------------------------
    def build_cli_args(self, request: GenerationRequest, prompt: Optional[str] = None):
        """
        GenerationRequest → `python -m cube3d.generate ...` 인자 리스트.

        - prompt 를 명시하지 않으면 내부 prompt_builder 로 생성.
        - use_bounding_box=True 이면 guide_ratio 를 --bounding-box-xyz 로 전달.
          (원본 절대 dimension 이 아니라 **정규화 비율** 을 넘긴다 = 연구 의도)
        반환: (args:list[str], meta:dict)  meta 는 diagnostics 용.
        """
        if prompt is None:
            prompt = self._build_prompt(request)

        cfg = self.config
        args = [
            cfg.python_exe,
            "-m", "cube3d.generate",
            "--gpt-ckpt-path", cfg.gpt_ckpt,
            "--shape-ckpt-path", cfg.shape_ckpt,
            "--prompt", prompt,
            "--output-dir", cfg.output_dir,
            "--resolution-base", str(cfg.resolution_base),
        ]
        if cfg.config_path:
            args += ["--config-path", cfg.config_path]
        if cfg.fast_inference:
            args += ["--fast-inference"]

        passed_bbox = None
        if cfg.use_bounding_box and request.guide_ratio:
            passed_bbox = [float(v) for v in request.guide_ratio]
            args += ["--bounding-box-xyz"] + [str(v) for v in passed_bbox]

        meta = {
            "prompt": prompt,
            "guide_dimensions": list(request.guide_dimensions),
            "guide_ratio": list(request.guide_ratio),
            "passed_bounding_box": passed_bbox,   # 실제 CLI 로 전달된 bbox
            "fast_inference": cfg.fast_inference,
            "resolution_base": cfg.resolution_base,
        }
        return args, meta

    # ------------------------------------------------------------------
    # 2) 사전 점검: 설치/weight/venv 존재 여부 (모델 로딩 없이 빠르게 실패)
    # ------------------------------------------------------------------
    def preflight(self):
        """
        실행 전 필수 리소스 존재를 점검한다. 문제가 있으면 사유 문자열 반환, 없으면 None.
        (production pipeline crash 방지: 여기서 명확히 걸러낸다.)
        """
        cfg = self.config
        if not os.path.isfile(cfg.python_exe):
            return "Cube3D venv python not found: {0}".format(cfg.python_exe)
        if not os.path.isdir(cfg.repo_dir):
            return "Cube3D repo not found: {0}".format(cfg.repo_dir)
        if not os.path.isfile(cfg.gpt_ckpt):
            return "model weights not found: {0}".format(cfg.gpt_ckpt)
        if not os.path.isfile(cfg.shape_ckpt):
            return "model weights not found: {0}".format(cfg.shape_ckpt)
        return None

    # ------------------------------------------------------------------
    # 3) 결과 판정: stdout/stderr + 예상 OBJ 경로 → 성공/실패 분류
    # ------------------------------------------------------------------
    @staticmethod
    def classify_failure(returncode: int, stderr: str) -> Optional[str]:
        """
        subprocess 실패를 사람이 읽는 사유로 분류한다. 성공이면 None.
        (CUDA/VRAM 부족 등 흔한 케이스를 힌트로 매핑.)
        """
        if returncode == 0:
            return None
        low = (stderr or "").lower()
        if "out of memory" in low or "cuda out of memory" in low:
            return "CUDA out of memory (VRAM insufficient). Try without --fast-inference or lower --resolution-base."
        if "no cuda" in low or "cuda is not available" in low or "no gpu" in low:
            return "CUDA/GPU not available."
        if "no module named" in low or "modulenotfounderror" in low:
            return "Cube3D not installed in the target venv (ModuleNotFoundError)."
        if "safetensors" in low and ("not found" in low or "no such file" in low):
            return "model weights not found."
        return "Cube3D subprocess failed (returncode={0}).".format(returncode)

    def expected_output_path(self, output_name: str = "output") -> str:
        return os.path.join(self.config.output_dir, "{0}.obj".format(output_name))

    # ------------------------------------------------------------------
    # 4) 실제 실행 (subprocess). 실패해도 예외를 던지지 않고 결과로 감싼다.
    # ------------------------------------------------------------------
    def generate(self, request: GenerationRequest, _runner=None) -> GenerationResult:
        """
        전체 흐름: preflight → CLI args → subprocess → OBJ 확인.

        _runner 는 테스트 주입용 (subprocess.run 대체). None 이면 실제 실행.
        어떤 실패도 GenerationResult(success=False, error=...) 로 반환한다.
        """
        prompt = self._build_prompt(request)
        args, meta = self.build_cli_args(request, prompt)

        # (a) 사전 점검
        problem = self.preflight()
        if problem is not None:
            return GenerationResult(
                success=False,
                request_master_id=request.master_id,
                error="[CUBE3D_ERROR] Generation failed for {0}\nReason: {1}".format(
                    request.master_id, problem),
                diagnostics={"cli_args": args, **meta},
            )

        os.makedirs(self.config.output_dir, exist_ok=True)

        # (b) subprocess 실행 (예외 방어)
        runner = _runner or self._default_runner
        try:
            proc = runner(args, self.config.repo_dir, self.config.timeout_sec)
        except subprocess.TimeoutExpired:
            return GenerationResult(
                success=False,
                request_master_id=request.master_id,
                error="[CUBE3D_ERROR] Generation failed for {0}\nReason: timeout after {1}s".format(
                    request.master_id, self.config.timeout_sec),
                diagnostics={"cli_args": args, **meta},
            )
        except Exception as exc:  # noqa: BLE001 - 외부 프로세스는 무엇이든 던질 수 있다
            return GenerationResult(
                success=False,
                request_master_id=request.master_id,
                error="[CUBE3D_ERROR] Generation failed for {0}\nReason: subprocess launch error: {1}".format(
                    request.master_id, exc),
                diagnostics={"cli_args": args, **meta},
            )

        stdout = getattr(proc, "stdout", "") or ""
        stderr = getattr(proc, "stderr", "") or ""
        rc = getattr(proc, "returncode", 1)

        # (c) 실패 분류
        reason = self.classify_failure(rc, stderr)
        if reason is not None:
            return GenerationResult(
                success=False,
                request_master_id=request.master_id,
                stdout=stdout, stderr=stderr,
                error="[CUBE3D_ERROR] Generation failed for {0}\nReason: {1}".format(
                    request.master_id, reason),
                diagnostics={"cli_args": args, **meta},
            )

        # (d) OBJ 산출 확인 (returncode 0 이어도 파일 없으면 실패)
        out_path = self.expected_output_path()
        if not os.path.isfile(out_path):
            return GenerationResult(
                success=False,
                request_master_id=request.master_id,
                stdout=stdout, stderr=stderr,
                error="[CUBE3D_ERROR] Generation failed for {0}\nReason: output OBJ not found at {1}".format(
                    request.master_id, out_path),
                diagnostics={"cli_args": args, "expected_output": out_path, **meta},
            )

        return GenerationResult(
            success=True,
            request_master_id=request.master_id,
            output_path=out_path,
            stdout=stdout, stderr=stderr,
            diagnostics={"cli_args": args, **meta},
        )

    @staticmethod
    def _default_runner(args, cwd, timeout):
        """
        실제 subprocess 실행 (stdout/stderr 캡처).

        stdin=DEVNULL: 부모(Blender 등)의 stdin 을 그대로 상속하면 환경에 따라
        비정상적으로 동작할 수 있어, 어떤 interactive 입력도 기대하지 않는다는 것을
        명시적으로 고정한다.
        """
        return subprocess.run(
            args, cwd=cwd, capture_output=True, text=True, timeout=timeout,
            stdin=subprocess.DEVNULL,
        )