# Semantic Graybox

> **Structure = Human Guidance. Form = Generative Freedom.**

Human-guided structural control for generative 3D asset workflows.

**Status:** research prototype, v0.3.1 baseline.

## Research reports

- **[Korean Research Report (국문)](docs/RESEARCH_PAPER_KO.md)** — design, experiments, limitations, and future work
- **[English Research Report](docs/RESEARCH_PAPER_EN.md)** — English translation of the preliminary technical report

Both documents are **independent, preliminary technical reports (not peer-reviewed)**. Experimental logs and some third-party or private assets are not included in this public repository; the reports distinguish measured results from proposed future integrations.

Semantic Graybox lets an artist author a low-cost Blender graybox that carries structural intent—semantic part roles, anchors, orientation, relative proportions, repeated-part relationships, and placement slots. The system turns that structure into generator-neutral `GenerationRequest` units, sends them through an external generator adapter, then places generated geometry back into Blender for human review.

## Pipeline

```text
Blender Graybox
      ↓
Semantic Blueprint
      ↓
GenerationRequest[]
      ↓
Generator Adapter
      ↓
External 3D Generator
      ↓
Automatic Placement / Instancing
      ↓
Human Semantic Review
```

## Current scope

- Semantic Blueprint extraction
- Unique-part / repeated-master decomposition
- Sequential generation queue
- Linked instancing for repeated masters
- Blender placement and safe cleanup
- Human semantic review with append-only JSONL evidence
- External Cube3D adapter boundary

Cube3D source code and model weights are **not included** and are **not covered by this repository's MIT License**.

## Current limitations

This is not production-ready.

- Semantic mapping is still partly name-based.
- Parent/entity context needs stronger handling for ambiguous names.
- Stock Cube3D v0.5 has not been shown to reliably generate isolated furniture parts for the current requests.
- Synthetic Blender fixtures under `tests/` are regression fixtures only, not semantic-quality benchmarks.
- User-authored `.blend` assets and generated meshes are intentionally excluded.

## License

Original Semantic Graybox source code in this repository is licensed under the MIT License. Third-party software, models, runtimes, and dependencies remain subject to their own licenses.
