# Project Status

## Public baseline

This repository publishes the **Semantic Graybox v0.3.1 control/workflow layer**:

- Blender graybox -> Semantic Blueprint
- Unique/master decomposition
- `GenerationRequest[]`
- Sequential generation queue
- Blender placement / linked instancing
- Human semantic result review
- Append-only review evidence

Execution success and semantic success are intentionally treated as different things.

## Generator capability is still under evaluation

A generator returning an OBJ is not enough to count as semantic success. Generated geometry must be reviewed against the requested part role and guide intent.

The current stock Cube3D integration has shown a recurring failure mode where isolated-part requests can produce whole-furniture-like geometry. This is treated as a generator-capability research problem rather than hidden behind execution success.

## Sampling finding

The tested stock production path used deterministic argmax sampling. Repeating the same request produced effectively identical geometry, so a planned repeated-trial baseline was stopped instead of counting duplicates as independent samples.

A stochastic evaluation condition must be explicitly justified and validated before reporting repeated-trial acceptance rates.

## Fixture correction

An early Generator Capability Review attempt used a synthetic Bed regression fixture rather than the user's real authored `.blend` asset. The determinism/sampling finding remains useful, but that fixture run is **not treated as a semantic baseline for the real asset**.

Fixtures under `tests/` are test assets only.

## Next research step

Before further generator-quality claims:

1. Use the actual authored source asset as the source of truth.
2. Audit exact extracted object names and resulting `GenerationRequest[]`.
3. Separate request-mapping errors from generator errors.
4. Only then run and human-review generator outputs.

A known motivation for this audit is ambiguous name mapping: generic names such as `Back` can receive a chair-oriented semantic label even when the parent entity is a bed. Parent/entity context therefore needs stronger treatment.

## Scope

This repository is a research prototype, not a finished production tool or pretrained 3D model.
