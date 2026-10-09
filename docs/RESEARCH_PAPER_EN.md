# Semantic Graybox: Design and Preliminary Evaluation of a Human-Guided Generative 3D Asset Pipeline

**의미 기반 그레이박스를 활용한 인간 주도형 생성형 3D 에셋 제작 파이프라인 설계 및 예비 평가**

> **Independent Research — Preliminary Technical Report**  
> Language: English · Document version: 0.1 · Reference date: 2026-10-09  
> System baseline: Semantic Graybox v0.3.1  
> Status: Public research draft / not peer-reviewed  
> Repository: [semantic-graybox](https://github.com/ang9089098-cpu/semantic-graybox)  
> Original Korean report: [RESEARCH_PAPER_KO.md](RESEARCH_PAPER_KO.md)

**Design principle: Structure = Human Guidance; Form = Generative Freedom.**

## Abstract

Generative AI offers new methods for producing three-dimensional geometry, yet producing a valid mesh does not necessarily satisfy an artist's intended part identity, repetition relationships, or spatial arrangement. This report proposes **Semantic Graybox**, a human-guided asset production pipeline in which artists define structural intent with simplified Blender geometry while an external generative model produces candidate forms. The system extracts a Semantic Blueprint from Blender collections and objects, including semantic grouping, dimensions, spatial anchors, and repeated-part relationships. It translates this blueprint into generator-neutral requests, executes a sequential generation queue, places or instances meshes into their original structural slots, and separately records human judgments of semantic suitability.

Preliminary experiments examine geometry responses to guide aspect ratios, controlled mesh reconstruction in the Cube3D VQ representation, repeated-part clustering, semantic-role embeddings, autoregressive conditioning, and the validity of repeated generation trials. The experiments demonstrate an implementable structural-control and placement workflow and observable geometric responses to ratio guidance. However, improvements in internal conditional-prediction metrics did not consistently produce better part-level semantics, and a deterministic sampling path created duplicate outputs unsuitable as independent trials. The current contribution is therefore **a working system for preserving artist-defined structural intent**, not a claim of reliable isolated-part generation or measured gains in production efficiency.

**Keywords:** Semantic Graybox, Generative 3D, Human-in-the-loop, Semantic Control, Blender, Technical Art, Asset Pipeline

---

## 1. Introduction

### 1.1 Motivation

Game environment production requires more than visually plausible single objects. It must preserve part decomposition, repetition, spatial placement, editability, and downstream integration. In a text-to-3D workflow, “one leg of a bed” and “a complete bed” are distinct requests. In the particular Cube3D v0.5 execution path studied here, requests for isolated parts sometimes produced meshes resembling whole furniture objects.

This observation is **not** asserted as a universal limitation of generative 3D. Instead, it motivates separating **the form-generation responsibility of a model** from **the semantic and spatial structure authored by the artist**.

### 1.2 Research questions

- **RQ1 — Representation:** Can Blender grayboxes be translated into structured semantic and spatial generation requests?
- **RQ2 — Execution:** Can unique and repeated parts be managed at the level of generation units rather than one generation per object?
- **RQ3 — Conditioning:** How do proportional guidance and semantic-role conditioning affect produced geometry?
- **RQ4 — Evaluation:** Can execution success be distinguished from human assessment of semantic adequacy?

### 1.3 Contributions and scope

This work studies a **generator-independent production-control layer**, not a new 3D foundation model. Its principal contributions are:

1. A Blender-derived **Semantic Blueprint** representation.
2. Separation of **unique parts, repeated masters, and placement slots**.
3. A **GenerationRequest — Generator Adapter — FIFO Queue** interface.
4. Automatic Blender placement and shared-mesh instancing.
5. **Human Semantic Review**, immutable request snapshots, and append-only review logs.
6. Preliminary Cube3D experiments on geometry, representation, role conditioning, and sampling behavior.

Throughout this report, implemented behavior, observed experimental results, and generalizable performance claims are treated as distinct levels of evidence.

## 2. Related technology

### 2.1 Generative 3D and representation

NeRF [1] and 3D Gaussian Splatting [2] are important approaches to representing and rendering three-dimensional scenes. However, this work concerns **editable mesh parts and their assembly**, rather than novel-view synthesis, so their rendering quality is not treated as a direct experimental baseline.

Roblox Cube [3] investigates 3D shape tokenization and generation. The current prototype invokes a separately installed **Cube3D v0.5** runtime as an external generator. Cube3D source code and weights are not claimed as contributions of Semantic Graybox.

### 2.2 Part-level semantics

PartNet [4] introduces a large-scale dataset of 3D objects with fine-grained and hierarchical part annotations. This research shares the emphasis on part-level representation but differs in its entry point: instead of decomposing a finished mesh, **the artist declares intended parts and spatial relations before generation**, using a simplified graybox. No PartNet training or evaluation has been completed in this project.

## 3. System design

### 3.1 Human-guided structure

**Structure = Human Guidance; Form = Generative Freedom.**

The artist determines which parts exist and how they relate spatially; the generator proposes their detailed geometry. Graybox dimensions and anchors represent **soft guidance** about proportions and arrangement. The default approach does not forcibly fit generated geometry into every guide box using non-uniform scaling.

### 3.2 Architecture

~~~text
Blender Graybox / Collection
             ↓
Semantic Graybox Extractor
             ↓
Semantic Blueprint
  ├─ Entity / Part Identity
  ├─ Transform / Anchors / Dimensions
  ├─ Topology / Constraints
  └─ Unique Parts / Masters / Slots
             ↓
GenerationRequest[]
             ↓
Prompt Builder + FIFO Queue
             ↓
Generator Adapter → External Cube3D
             ↓
OBJ Import → Placement / Shared Instancing
             ↓
Human Semantic Review → JSONL Events
~~~

Backend-specific operations are isolated within the adapter. The current Cube3D adapter invokes a separate Python subprocess, keeping Blender's Python environment independent from the GPU model runtime. This provides **an extensible boundary**, not evidence that every alternative generator has already been integrated or validated.

### 3.3 Semantic Blueprint

| Component | Extracted information | Purpose |
|---|---|---|
| Entity | Collection name and metadata | Parent-object context |
| Part | Object name, group key, directional hints | Candidate part identity |
| Transform | World-space location, rotation, scale | Placement |
| Anchor | Origin, bbox center/bounds, dimensions | Spatial guidance |
| Topology | Parent–child links | Structural relations |
| Master | Repeated group and representative dimensions | Shared generation |
| Slot | Per-original-object placement | Instancing |
| Constraint | Equal-dimension and certain ratio relations | Relational guidance |

Some semantic interpretation currently depends on naming conventions. Generic names such as “Back” and “Front” can be interpreted incorrectly when the parent entity is a bed rather than another furniture category. Robust parent-context-sensitive role mapping remains a research task.

### 3.4 Repeated parts and generation units

The system distinguishes **geometry identity** from **placement identity**. Guides within the same semantic group that satisfy size-similarity criteria are represented by one master, while their original transforms and directional information remain in separate slots.

~~~text
Leg_01 ─┐
Leg_02 ─┼─→ Master A → 1 generation → 3 placement slots
Leg_03 ─┘

Leg_04 ───→ Master B → 1 generation → 1 placement slot
~~~

Directional suffixes serve placement and labeling purposes rather than arbitrarily determining geometry clusters. Similar graybox dimensions do not, by themselves, guarantee interchangeability of finished meshes.

### 3.5 Sequential execution and placement

Generation units execute in FIFO order to avoid concurrent GPU pressure. Each unit receives its own output path to prevent accidental overwrites. Failure of one unit does not automatically roll back previously completed units. Original guides are preserved, and cleanup is restricted to unkept results owned by the Semantic Graybox tool.

### 3.6 Human Semantic Review

**Execution states:** PENDING, GENERATING, DONE, ERROR, KEPT  
**Semantic review states:** UNREVIEWED, ACCEPTED, REJECTED

Rejection categories include WRONG_PART, WHOLE_OBJECT, BROKEN_MESH, WRONG_PROPORTION, and OTHER. Review events retain the original request, final prompt, guidance information, output identity, and available diagnostics. They are appended to a JSONL log rather than overwriting earlier judgments.

This is a **human evaluation and evidence-preservation layer**, not an automatic classifier or online learning procedure.

## 4. Experiments and results

### 4.1 Environment and evidence categories

The primary development and evaluation environment used **Blender 5.2.2 LTS**, **Cube3D v0.5**, and an **NVIDIA RTX 5070 Ti with 16 GB VRAM**.

Three kinds of evidence must be distinguished: **system regression tests**, **geometry/generator experiments**, and **human semantic judgments**. A returned OBJ, connected-component count, aspect ratio, or teacher-forced loss margin does not establish semantic suitability of a generated part.

### 4.2 E1: Geometric response to guide ratios

Using the fixed prompt “A rococo carved furniture leg for a desk,” the experiment varied the bbox guidance ratio without post-generation non-uniform fitting.

| Condition | Input ratio | Observed elongation ratio | Wall time |
|---|---|---:|---:|
| A0 | No bbox guidance | About 1.64 | 72.1 s |
| A1 | 1:1:4 | About 4.11 | 75.5 s |
| A2 | 1:1:8.75 | About 9.72 | 72.4 s |
| A3 | 1:1:12 | About 11.07 | 80.9 s |

All four generations completed. Output elongation increased in the same order as the input ratios, supporting an **observable geometric conditioning effect in this tested runtime**.

The experiment used **one generation per condition**, did **not perform a visual judgment of furniture-leg identity**, and did **not establish run-to-run variation**. Geometric elongation should not be conflated with semantic correctness.

### 4.3 E2: Controlled VQ shape reconstruction

Five locally created leg-like control meshes and one complete-desk control were passed through the **unmodified Cube3D VQ encoder and decoder**. No text conditioning, bbox generation guidance, or additional training was involved.

| Control geometry | Result | Observation |
|---|---|---|
| L0 simple leg | PASS | Basic silhouette preserved |
| L1 tapered leg | DEGRADED | Components 1→10; cross-sectional distortion |
| L2 curved leg | PASS | Curved silhouette preserved |
| L3 ornamented leg | PASS | Curvature and ornament outlines preserved |
| L4 extremely thin leg | PASS | Very thin shape preserved |
| Complete desk | PASS | Overall structure recognizable |

All **six of six encodings and decodings succeeded mechanically**; the predefined reconstruction assessment classified **five as PASS and one as DEGRADED**. One tapered sample is insufficient to demonstrate a general failure pattern for tapering.

These results support **representation feasibility on a small controlled set**, not the ability of a free-generating model to select and produce isolated semantic parts from a prompt.

### 4.4 E3: Master clustering correction and real generation

A controlled Desk scene contained three legs with equivalent dimensions and one leg with different dimensions. The original implementation unexpectedly produced a **2:2 split**. After revising size-based clustering, the resulting groups matched the intended **3:1 split**.

| Measure | Validated result |
|---|---|
| Master groups | 2: three slots + one slot |
| Actual Cube3D calls | 2 |
| Blender placements | 4 |
| Shared geometry | Three slots share one mesh datablock |
| Outlier guide | Separate generated mesh |
| Source guides | Preserved |
| Generation times | 80.27 s and 81.11 s |

The experiment also separated master output directories to prevent overwrites. This validates **independent control over generation calls and placement counts**. It does not measure an actual productivity speedup over four independently generated objects.

### 4.5 E4: Multi-part queue and Human Review regression

The v0.3 prototype implemented a multi-part sequential queue and Blender placement. Version v0.3.1 added per-unit acceptance/rejection, request snapshots, and append-only event logs.

The v0.3.1 worklog records **59 passing Python tests** and successful Blender smoke tests for the legacy workflow, multi-part queue, and semantic-review interface. The v0.3.1 manual UI validation used a **mock Bed scene and mock generator**; it did not rerun GPU generation or evaluate genuine semantic quality.

A prior real Bed end-to-end generation had completed execution and placement while still producing whole-furniture-like forms for requests intended as isolated parts. The workflow therefore explicitly separates **execution success from semantic success**.

### 4.6 E5: T0 semantic-role embeddings

A small trainable role embedding distinguished LEG and TOP while the original Cube3D backbone was frozen. This section follows the **later trained R0/R1/R2 generalization and free-generation reports**, rather than the initial plumbing-only dry-run README.

| Run | Holdout teacher-forced mean margin | Free-generation observation |
|---|---:|---|
| R0 | +0.3016 | No clear role-consistent directional contrast |
| R1 | +0.1581 | Clearest relative role-linked form contrast |
| R2 | +0.1031 | Some differentiation, but ambiguous |

Teacher-forced margins ranked **R0 > R1 > R2**, while the observed clarity of free-generation differences did not follow that order. Internal conditional prediction metrics therefore cannot be assumed to replace an evaluation of generated part semantics.

The experiment used **13 locally created synthetic shapes**, a binary LEG/TOP role vocabulary, and limited generation conditions. It did not establish general furniture-part generation quality or production reliability.

### 4.7 E6: KV-cache and repeated conditioning

Autoregressive diagnostics found that the role-bearing conditioning tensor was mainly processed at the prefill stage in the cached path. A **no-cache diagnostic control** was used to recompute existing conditioning at every token step.

- No-cache generation was about **3.2–3.3× slower** than cached generation.
- For R1, the LEG/TOP elongation gap decreased from **1.0464 to 0.4236**.
- For R2 TOP, connected components increased from **2 to 254**.
- First-token equivalence and deterministic reruns validated the basic control behavior.

In this controlled setup, **making the existing role signal available more often did not improve semantic steering**. The gate classification was **NC-C**, and the planned trainable **T1-A adapter was neither implemented nor trained**.

This is descriptive evidence from **three checkpoints and one seed/bbox condition**, not a general model-level performance claim.

### 4.8 E7: Deterministic sampling and trial validity

The GCR-A0-S0 investigation found that the production adapter used a default **top_p=None** setting that selected **argmax tokens** in the installed runtime.

Two runs of an identical LEG request produced **byte-identical OBJ files with identical geometry**. Counting such duplicates as independent semantic trials would misrepresent the sample size, so the originally proposed five-runs-per-role design was stopped.

Actual GPU invocations were **two LEG, one HEADBOARD, and one SIDE_FRAME: four in total**. All four executions completed, but **no human semantic accept/reject decisions were recorded** for these diagnostic outputs.

**Crucial provenance limitation:** the GCR Bed was a **synthetic v0.3 test fixture**, not the artist's actual working Bed.blend file. This experiment is **not** a semantic baseline for the real asset. The observed determinism is limited to the tested runtime, prompt, and sampling configuration.

## 5. Discussion

### 5.1 Structural control versus semantic fidelity

Evidence supports implementing (a) explicit structural representation, (b) generation units for unique/repeated parts, (c) placement and linked instancing, (d) separate human review records, and (e) geometric responses to proportional guidance in a restricted experiment.

It does **not yet demonstrate** reliable isolated-part semantic generation, generalization across many asset types, improvements in final asset quality, or reduced artist production time.

### 5.2 Reconstruction capability is not conditional generation

A VQ tokenizer that reconstructs isolated geometry does not necessarily enable a text- or role-conditioned generator to **select and create** that same part reliably. Likewise, a mesh with a plausible aspect ratio is not necessarily semantically identifiable as a furniture leg. These tasks need distinct measurements.

### 5.3 Negative findings as research evidence

The erroneous 2:2 clustering split, mismatch between training proxy and free-generation results, no-cache degradation, and duplicate deterministic trials each informed a **revision or stop decision**. Preserving these negative findings is necessary for an accurate research record.

### 5.4 Future pipeline extensions

Possible long-term extensions include mesh cleanup, UV/PBR materials, USD interchange, Blender-to-Unreal workflows, and procedural scene placement. **End-to-end integration with InstaMAT, VIGA, 3DGS, NeRF, USD, or Unreal PCG is not demonstrated by this report** and must not be presented as an implemented result.

## 6. Limitations and future work

1. **Small evaluation scale:** A single research workflow and a limited number of controlled geometries.
2. **Insufficient real-asset baseline:** GCR-A0-S0 used a synthetic Bed fixture.
3. **Incomplete human judgment:** Its four GPU outputs lack human semantic decisions.
4. **Duplicate sampling risk:** Deterministic argmax repeats cannot be treated as independent trials.
5. **Name-based semantic ambiguity:** Part names such as Back/Front need parent-aware mapping.
6. **No productivity comparison:** Time, rework, and quality were not compared against manual or unstructured workflows.
7. **Partial reproducibility:** Some source experiments, personal Blender assets, model weights, and large outputs are not included in the public repository.

The next defensible sequence is **audit request mappings from the real Bed.blend → validate a controlled stochastic trial configuration → collect genuine human reviews → compare generator candidates**. New trainable conditioning mechanisms should be evaluated after these prerequisites.

## 7. Conclusion

Semantic Graybox proposes a **human-guided 3D production architecture** in which artists retain structural intent while an external generative model provides form proposals. The Semantic Blueprint, master/slot decomposition, adapter-based queue, Blender placement, and Human Semantic Review have been implemented as a functioning research prototype.

However, geometric aspect-ratio guidance, reconstruction capability, and improvements in internal conditioning metrics did **not** establish reliable semantic correctness of isolated generated parts. The current contribution is therefore not a superior generative model but **a production-control system that preserves artist-authored structure and evaluates execution and semantic success separately**.

---

## References

[1] B. Mildenhall et al., “NeRF: Representing Scenes as Neural Radiance Fields for View Synthesis,” *ECCV*, 2020. https://doi.org/10.1007/978-3-030-58452-8_24

[2] B. Kerbl, G. Kopanas, T. Leimkühler, and G. Drettakis, “3D Gaussian Splatting for Real-Time Radiance Field Rendering,” *ACM Transactions on Graphics*, 42(4), Article 139, 2023. https://doi.org/10.1145/3592433

[3] Roblox Foundation AI Team et al., “Cube: A Roblox View of 3D Intelligence,” *arXiv:2503.15475*, 2025. https://arxiv.org/abs/2503.15475

[4] K. Mo et al., “PartNet: A Large-Scale Benchmark for Fine-Grained and Hierarchical Part-Level 3D Object Understanding,” *CVPR*, pp. 909–918, 2019. https://doi.org/10.1109/CVPR.2019.00100

## Evidence provenance and reproducibility notice

The experimental numbers in this report are derived from the following **local project records**. Some are not included in this public GitHub repository due to third-party licensing, private assets, or large generated outputs. These paths are identifiers, **not working public links**. Therefore, external reproduction and independent review are **not yet complete**.

| Topic | Source record (local, partly unpublished) |
|---|---|
| Guide ratios | experiments/guide_ratio/RESULTS.md |
| VQ round-trip | experiments/vq_part_roundtrip/CONTROL_ROUNDTRIP_RESULTS.md |
| Master clustering | experiments/master_clustering/RESULTS.md |
| Multi-part queue | WORKLOG_2026-10-02_v03.md |
| Human review | MILESTONE_SEMANTIC_GRAYBOX_v0.3.1.md; WORKLOG_2026-10-02_v031.md |
| T0 generalization | experiments/semantic_role_t0/generalization/GENERALIZATION_RESULTS.md |
| T0 free generation | experiments/semantic_role_t0/free_generation/phase12/report.md |
| Autoregressive diagnostics | experiments/semantic_role_t0/autoregressive_diagnostic/T0-D1/report.md |
| No-cache control | experiments/semantic_role_t1/report.md |
| GCR-A0-S0 | experiments/generator_capability_review/stock_cube3d/report.md; sampling_audit.md |

This report is a **preliminary technical report and has not been peer-reviewed**. The repository's MIT license applies only to its original Semantic Graybox source code; Cube3D/CubePart and all external dependencies retain their respective licenses. See [Third-Party Notices](../THIRD_PARTY_NOTICES.md).
