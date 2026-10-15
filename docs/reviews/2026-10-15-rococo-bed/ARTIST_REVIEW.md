# Artist Review: Correct Placement Does Not Resolve Part Semantics

Date: 2026-10-15 (Asia/Seoul)  
Source: direct artist feedback and three artist-supplied Blender screenshots  
Scope: real `Bed.blend`, rococo, Trial 01, seed `20261001`, assembled `BBOX_PROXY` view

## Main finding

The artist reports that the generated outputs now occupy the intended positions and overall sizes in the shown assembly. **Except for the headboard, the outputs still look like scaled or deformed rococo desks/furniture rather than the requested isolated bed parts.**

This is evidence that placement and scale calibration can work while part semantics still fail. The current result does not establish a successful bed-part generation workflow.

The headboard is an exception in this qualitative feedback. It is **not automatically recorded as a formal ACCEPTED sample**, and this single assembly is not a verdict on all 40 baseline samples or both styles.

## Artist observation

English translation of the artist's feedback:

> The results are now placed at the correct positions and sizes, but except for the headplate, they are just rococo desks scaled and deformed to fit.

The observation is recorded as supplied. Shape names such as “desk-like” describe the artist's reading of the outputs; they are not an automated geometry classification.

## What each colour and source unit represents

| Source unit | Requested role | Display | Artist observation for this assembly |
|---|---|---|---|
| `Back` | Headboard | Orange | Named as the exception to the reported failure; no formal acceptance inferred |
| `Front` | Footboard | Purple | Included in the reported non-headboard failure: wrong furniture/part content remains |
| `Master_Leg` from `Leg`, `Leg.001`, `Leg.002`, `Leg.003` | One leg master, four linked placements | Blue | Included in the reported failure; correct leg-slot placement does not make the generated shape a valid leg |
| `Mattress` | Mattress | Green | Included in the reported failure; the output does not provide the intended mattress according to the artist |

The green geometry is the **actual cached Mattress-request output**, even where it resembles a furniture frame. It is not a newly modelled side-frame replacement.

When guides are visible, the grey slab and other grey blocks are the **original source guides**. The grey slab must not be counted as a successfully generated mattress.

## Evidence supplied by the artist

The artist supplied three Blender screenshots: generated-only assembly, source/generated Outliner, and assembly with original grey guides overlaid. The images are retained locally and are not included in this public update pending explicit authorization for public image disclosure.

The supplied Outliner identifies `ROCOCO_T01_BBOX_PROXY` and all seven generated placements corresponding to the source guides. In the guide-overlay view, the grey mattress slab and other grey blocks remain original reference geometry.

The structured observation and its scope are recorded in [artist_observation.json](artist_observation.json).

## Missing parts: semantic absence versus missing files

The cached experiment has outputs for all four declared request units. This observation therefore concerns **incorrect or absent required part content inside existing outputs**, rather than a missing output file.

In particular:

- A furniture-like result in a leg slot is still a part-semantic failure.
- A frame-like Mattress-request result does not supply a mattress merely because its position and extent are suitable.
- The original grey Mattress guide is preserved reference geometry, not a generated result.
- Side frames were not declared in the actual source/request contract. Their absence is distinct from a requested unit that failed to produce an output.

## What the assembly experiment changed

The assembled comparison reuses the existing stock Cube3D outputs. The numerical proxy view applies **one uniform scale and a translation** using a role-specific reference length and bbox-face proxy. It does not edit mesh vertices, stretch separate axes, regenerate geometry, or replace bad parts with newly modelled assets.

The artist's “scaled/deformed” description concerns the resulting appearance. The unwanted whole-furniture-like content already exists in the cached generated meshes; this report does not claim that assembly calibration converted a correctly generated leg into a desk.

Greyboxes remain references for structural intent, form, scale, and placement. They are not hard containers, and ornamental protrusions are not by themselves a semantic failure.

## Evidence boundaries and review status

The local controlled baseline contains two styles × four units × five seeds = **40 evaluation outputs**, plus two excluded reproducibility controls. That execution pool is not the scope of the artist's single displayed-assembly observation.

Before this documentation update, the verified local audit recorded:

| Check | Recorded result | What it establishes |
|---|---|---|
| Evaluation outputs | 40 DONE | Execution/file completion only |
| Cached assembly coverage | Ten style/seed combinations, four units and seven placements per view | Coverage and source-to-output identity |
| Comparison views | 20 scenes / 140 display placements | Raw and proxy placement of the same geometry |
| Reloaded numerical proxy checks | Passed | Declared reference-length and bbox-proxy alignment, not functional joint quality |
| Existing tests / new assembly boundary tests | 59 / 8 passed | Regression and numerical boundary behaviour |
| Structural audit | 20/20 passed | Artifact identity, hashes, sampling records, source preservation |
| Protected local files | 204 hashes unchanged | Source assets, production code/tests, and referenced baseline evidence preserved |
| Formal per-sample UI review log | 1/40 reviewed; LEG T01 REJECTED / WRONG_PART | Incomplete formal semantic review |

This report adds a **qualitative human observation**. It does not append or overwrite production `semantic_reviews.jsonl`, manufacture per-unit UI review events, or calculate a final 40-sample acceptance rate. The latest formal-review count should be re-read from the local append-only log before any later aggregation.

The orange headboard's reported exception is not converted into a universal headboard success claim. The rococo T01 finding is not generalized to modern outputs or other seeds without inspection.

## Research implication and next validation

**Assembly correction has not resolved part-semantic generation.** Further progress should be measured against whether a generator produces the requested isolated role and required structure.

1. Complete role-specific human review using the existing outputs and original individual review scenes.
2. Record wrong-part/whole-object content and missing required features separately from placement, scale, file coverage, and intentional guide protrusion.
3. Compare a predeclared, limited semantic-control candidate only after identifying failing roles and checking its supported role vocabulary and sampling compatibility.
4. Preserve the same requests, bbox conditions, paired seeds, and review criteria when comparing a model variant. A prompt change is a separate experimental factor.
5. Revisit functional anchors and artist-facing assembly after semantically suitable parts are available. Do not count a resized wrong part as a semantic fix.

No production code, source assets, semantic-role research, model/runtime configuration, or generation outputs were changed for this GitHub update. No additional inference or training was run.

## Provenance

- Local controlled baseline: `GCR_A0_REAL`, batch `fe600f84f10e428c925f3f1cd9743415`.
- Cached assembly experiment: `GCR_CACHED_ASSEMBLY_20261015_01`, completed local execution directory `execution_20261015_02`.
- Displayed scene identified from the supplied Outliner: `ROCOCO_T01_BBOX_PROXY`.
- Source roles retain the approved experiment-only `Back=headboard`, `Front=footboard` overrides.
- Original source assets, meshes, and private/full experiment logs remain outside the public repository. This public report contains the qualitative observation; the supplied screenshots remain unpublished.

