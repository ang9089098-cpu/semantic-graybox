# Architecture

Semantic Graybox separates **artist-authored structure** from **generator-authored form**.

```text
Blender Collection
    ↓
semantic_graybox_extractor.py
    ↓
Semantic Blueprint
    ↓
generation/request.py
    ↓
GenerationRequest[]
    ↓
generation/prompt_builder.py
    ↓
generation/pipeline.py
    ↓
GeneratorAdapter
    ↓
External generator process
    ↓
OBJ
    ↓
generation/blender_import.py
    ↓
Generated collection / linked instances
    ↓
Human semantic review
```

## Structural representation

The graybox encodes parent entity context, semantic/group identity, world transform, anchors/bounds, relative guide dimensions, repeated-part/master relationships, placement slots, and topology.

The guide volume is not intended as an exact fitting cage.

## Generator separation

`GenerationRequest` is intentionally generator-neutral. Backend-specific details live in adapters.

The current Cube3D adapter runs Cube3D in a separate Python process, does not import PyTorch/Cube3D into Blender, converts guide ratio to backend CLI bbox conditioning, records diagnostics, and returns a neutral `GenerationResult`.

This allows future generators to be integrated without replacing the graybox representation, queue, placement, or review layers.

## Repeated parts

Repeated equivalent parts are generated once and instantiated into multiple slots.

```text
Leg.001
Leg.002
Leg.003
Leg.004
      ↓
Master_Leg
      ↓
one generation
      ↓
four linked Blender instances
```

The intended distinction is:

> placement identity is not geometry identity.

## Review layer

Generated units keep execution status separate from semantic review state.

Execution states include `PENDING`, `GENERATING`, `DONE`, `ERROR`, and `KEPT`.

Semantic review states are `UNREVIEWED`, `ACCEPTED`, and `REJECTED`.

Review decisions are human judgments and are written to an append-only JSONL research log. Automatic mesh metrics do not substitute for semantic acceptance.
