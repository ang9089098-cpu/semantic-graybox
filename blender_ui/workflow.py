"""Artist workflow state and lifecycle; no work is performed by Panel.draw."""
import json
import uuid
from concurrent.futures import ThreadPoolExecutor

from generation.pipeline import build_blueprint_from_collection, _apply_style
from generation.request import requests_from_blueprint
from generation.prompt_builder import build_prompt
from generation.semantic_review import SemanticReview, request_snapshot
from generation.review_log import record_review, review_log_path

OWNER = "semantic_graybox_owner"
RUN = "semantic_graybox_run"
KEPT = "semantic_graybox_kept"
TOOL = "semantic_graybox_v02"
_ACTIVE = None


def preview(blueprint, style):
    requests = _apply_style(requests_from_blueprint(blueprint), style)
    return build_prompt(requests[0]) if requests else "No generation units."


def refresh_preview(props, context):
    props.generated_prompt = preview(json.loads(props.blueprint_json), props.style_prompt) if props.blueprint_json else "Analyze Graybox to preview the prompt."
    if props.blueprint_json and hasattr(props, "units") and not props.queue_running:
        requests = _apply_style(requests_from_blueprint(json.loads(props.blueprint_json)), props.style_prompt)
        for item, request in zip(props.units, requests):
            item.prompt = build_prompt(request)


def reset_analysis(props, context):
    props.blueprint_json = ""
    props.entity = "Not analyzed"
    props.parts = props.masters = props.instances = 0
    props.gen_units = 0
    props.units.clear()
    props.status = "Target changed. Analyze Graybox."
    refresh_preview(props, context)


def analyze(props):
    assert_idle()
    collection = props.target_collection
    if collection is None:
        raise ValueError("Target Collection is not set.")
    if any(o.get(OWNER) == TOOL for o in collection.objects):
        raise ValueError("Choose a source guide collection, not generated output.")
    blueprint, _ = build_blueprint_from_collection(collection)
    if blueprint is None:
        reset_analysis(props, None)
        raise ValueError("No MESH parts found in Target Collection.")
    props.blueprint_json = json.dumps(blueprint)
    props.entity = blueprint["entity_type"]
    props.parts = blueprint["stats"]["total_mesh_parts"]
    masters = blueprint["components"]["master_parts"]
    props.masters = len(masters)
    props.instances = sum(m.get("instance_count", len(m.get("slots", []))) for m in masters)
    requests = _apply_style(requests_from_blueprint(blueprint), props.style_prompt)
    props.gen_units = len(requests)
    props.units.clear()
    master_ids = {m["master_id"] for m in masters}
    for request in requests:
        item = props.units.add()
        item.unit_id = request.master_id
        item.kind = "MASTER" if request.master_id in master_ids else "UNIQUE"
        item.instance_count = request.instance_count
        item.status = "PENDING"
        item.prompt = build_prompt(request)
    refresh_preview(props, None)
    props.status = "Ready" if requests else "No generation units."


def owned_objects(scene, run_id=None):
    return [o for o in scene.objects if o.get(OWNER) == TOOL and (run_id is None or o.get(RUN) == run_id)]


def clear_objects(objects, guides=()):
    import bpy
    protected = set(guides)
    count = 0
    for obj in objects:
        if obj in protected or obj.get(OWNER) != TOOL:
            continue
        mesh = obj.data if obj.type == "MESH" else None
        bpy.data.objects.remove(obj, do_unlink=True)
        if mesh and mesh.users == 0:
            bpy.data.meshes.remove(mesh)
        count += 1
    return count


def generate(context, props, base_dir, replace=False):
    assert_idle()
    import bpy
    from generation.pipeline import run_generation
    from generation.generator_adapters.cube3d_adapter import Cube3DConfig
    if not props.style_prompt.strip():
        raise ValueError("Style / Intent is empty.")
    analyze(props)  # Always use fresh source geometry, also for legacy operator calls.
    if not props.masters:
        raise ValueError("No repeated master to generate.")
    old = [o for o in owned_objects(context.scene, props.result_run) if not o.get(KEPT)] if replace and props.result_run else []
    cfg = Cube3DConfig.from_env(base_dir)
    if props.override_options:
        cfg.resolution_base = props.resolution_base
        cfg.timeout_sec = props.timeout_sec
        cfg.fast_inference = props.fast_inference
        cfg.use_bounding_box = props.use_bounding_box
    before = set(bpy.data.objects)
    props.status = "Generating..."
    try:
        outcome = run_generation(collection=props.target_collection, style_prompt=props.style_prompt.strip(), generator=props.generator, config=cfg, do_import=True, base_dir=base_dir)
    except Exception:
        clear_objects(set(bpy.data.objects) - before)
        raise
    new = [o for o in context.scene.objects if o not in before and o.get(OWNER) == TOOL]
    if not outcome.success:
        clear_objects(new)
        raise RuntimeError(outcome.message or "Generation failed.")
    run_id = uuid.uuid4().hex
    for obj in new:
        obj[RUN] = run_id
        obj[KEPT] = False
    if replace:
        clear_objects(old, props.target_collection.objects)
    props.result_run = run_id
    props.result_total = props.completed = props.failed = 0
    props.result_master = outcome.master_id or ""
    props.result_instances = len(new)
    props.result_collection = ", ".join(sorted({c.name for o in new for c in o.users_collection}))
    props.result_kept = False
    props.generated_prompt = outcome.final_prompt or props.generated_prompt
    props.status = outcome.message
    props.result_units.clear()
    item = props.result_units.add()
    item.unit_id, item.kind, item.status = outcome.master_id, "MASTER", "DONE"
    item.instance_count = outcome.request.instance_count
    item.run_id, item.has_geometry = run_id, bool(new)
    item.prompt = outcome.final_prompt
    blueprint = json.loads(props.blueprint_json)
    placement = next(m for m in blueprint['components']['master_parts'] if m['master_id'] == outcome.master_id)
    item.snapshot_json = json.dumps(request_snapshot(outcome.request, batch_id=run_id,
        unit_kind="MASTER", entity_type=blueprint['entity_type'], generator=props.generator,
        placement=placement, output_path=outcome.output_path, final_prompt=outcome.final_prompt,
        diagnostics=outcome.result.diagnostics), ensure_ascii=False)
    return outcome


def clear_result(props):
    for item in props.result_units:
        item.has_geometry = False
    props.result_run = props.result_master = props.result_collection = ""
    props.result_instances = 0
    props.result_kept = False
    props.completed = props.failed = props.result_total = 0


def assert_idle():
    if _ACTIVE is not None:
        raise RuntimeError("Generation queue is running. Wait until it finishes.")


def runtime_config(props, base_dir):
    from generation.generator_adapters.cube3d_adapter import Cube3DConfig
    cfg = Cube3DConfig.from_env(base_dir)
    if props.override_options:
        cfg.resolution_base = props.resolution_base
        cfg.timeout_sec = props.timeout_sec
        cfg.fast_inference = props.fast_inference
        cfg.use_bounding_box = props.use_bounding_box
    return cfg


class QueueSession:
    """Worker generates files; timer imports objects and updates UI on main thread."""
    def __init__(self, context, props, base_dir, replace=False):
        from generation.pipeline import GenerationQueue
        if not props.style_prompt.strip():
            raise ValueError("Style / Intent is empty.")
        # Regenerate retains the analyzed plan, style and guides, as specified.
        if not replace or not props.blueprint_json:
            analyze(props)
        blueprint = json.loads(props.blueprint_json)
        self.queue = GenerationQueue(blueprint, props.style_prompt.strip(), props.generator,
                                     runtime_config(props, base_dir))
        self.scene = context.scene
        self.view_layer = context.view_layer
        self.window = context.window
        self.props = props
        self.guides = list(props.target_collection.objects)
        self.old_run = props.result_run
        self.old = [o for o in owned_objects(self.scene, self.old_run) if not o.get(KEPT)] if replace and self.old_run else []
        self.replace = replace
        self.pool = None
        self.future = self.current = None
        self.generator = props.generator
        props.result_units.clear()
        for _ in self.queue.batch.results:
            props.result_units.add()
        props.queue_running = True
        props.result_run = self.queue.batch.run_id
        props.result_total = self.queue.batch.total
        props.result_kept = False
        self.sync()

    def sync(self):
        p, batch = self.props, self.queue.batch
        p.completed, p.failed = batch.completed, batch.failed
        p.result_master = ", ".join(u.unit_id for u in batch.results if u.success)
        objects = owned_objects(self.scene, batch.run_id)
        p.result_instances = len(objects)
        p.result_collection = ", ".join(sorted({c.name for o in objects for c in o.users_collection}))
        if len(p.units) != batch.total:
            p.units.clear()
            for _ in batch.results:
                p.units.add()
        for item, unit in zip(p.units, batch.results):
            item.unit_id, item.kind = unit.unit_id, unit.kind
            item.status, item.message = unit.status, unit.message
            item.instance_count = unit.request.instance_count
            item.prompt = build_prompt(unit.request)
        for item, unit in zip(p.result_units, batch.results):
            item.unit_id, item.kind = unit.unit_id, unit.kind
            item.status, item.message = unit.status, unit.message
            item.instance_count = unit.request.instance_count
            item.run_id = batch.run_id
            item.prompt = build_prompt(unit.request)
            item.has_geometry = unit.success and any(o.get('generation_unit_id') == unit.unit_id for o in objects)
            if unit.success and not item.snapshot_json:
                diagnostics = unit.result.diagnostics or {}
                item.prompt = diagnostics.get('prompt') or build_prompt(unit.request)
                item.snapshot_json = json.dumps(request_snapshot(unit.request,
                    batch_id=batch.run_id, unit_kind=unit.kind, entity_type=self.queue.entity,
                    generator=self.generator, placement=unit.placement, output_path=unit.output_path,
                    final_prompt=item.prompt, diagnostics=diagnostics), ensure_ascii=False)
        if batch.finished:
            p.status = batch.message
        elif self.current:
            p.status = "Generating {0} / {1} — {2}".format(
                batch.results.index(self.current) + 1, batch.total, self.current.unit_id)
        else:
            p.status = "Queue ready: {0} units".format(batch.total)

    def finish_session(self):
        # Replace only units that succeeded; failed replacements keep old output.
        if self.replace:
            succeeded = {u.unit_id for u in self.queue.batch.results if u.success}
            survivors = [o for o in self.old if o.get("generation_unit_id") not in succeeded]
            clear_objects([o for o in self.old if o.get("generation_unit_id") in succeeded], self.guides)
            for obj in survivors:
                # Carry forward failed replacements so the next Regenerate can replace them.
                obj[RUN] = self.queue.batch.run_id
        self.sync()
        self.props.queue_running = False
        if self.pool:
            self.pool.shutdown(wait=False)

    def run_sync(self):
        while True:
            self.current = self.queue.begin_next()
            if self.current is None:
                break
            self.sync()
            self.queue.finish(self.current, self.queue.generate(self.current))
            self.sync()
        self.finish_session()
        return self.queue.batch

    def tick(self):
        import bpy
        global _ACTIVE
        if self.future is not None:
            if not self.future.done():
                return .2
            result = self.future.result()
            # bpy operators run under the source scene even if the artist switches scenes.
            override = {"scene": self.scene, "view_layer": self.view_layer}
            if self.window:
                override["window"] = self.window
            try:
                with bpy.context.temp_override(**override):
                    self.queue.finish(self.current, result)
            except Exception as exc:
                from generation.generator_adapters.base import GenerationResult
                self.queue.finish(self.current, GenerationResult(False, self.current.unit_id, error=str(exc)))
            self.future = None
            self.sync()
        self.current = self.queue.begin_next()
        if self.current is None:
            self.finish_session()
            _ACTIVE = None
        else:
            self.sync()
            self.future = self.pool.submit(self.queue.generate, self.current)
        for window in bpy.context.window_manager.windows:
            for area in window.screen.areas:
                if area.type == "VIEW_3D":
                    area.tag_redraw()
        return None if self.queue.batch.finished else .2


def generate_all(context, props, base_dir, replace=False):
    import bpy
    global _ACTIVE
    assert_idle()
    session = QueueSession(context, props, base_dir, replace)
    if bpy.app.background:
        return session.run_sync()
    session.pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="SemanticGraybox")
    _ACTIVE = session
    bpy.app.timers.register(session.tick, first_interval=.1)
    return None


def keep_result(context, props):
    assert_idle()
    for obj in owned_objects(context.scene, props.result_run):
        obj[KEPT] = True
    for item in list(props.units) + list(props.result_units):
        if item.status == "DONE":
            item.status = "KEPT"
    props.result_kept = True
    props.status = "Result kept."


def reviewable_unit(context, props, unit_id, run_id):
    assert_idle()
    item = next((u for u in props.result_units if u.unit_id == unit_id and u.run_id == run_id), None)
    if item is None or item.status not in ('DONE', 'KEPT') or not item.has_geometry:
        raise ValueError('This completed result is no longer available for review.')
    if not any(o.get('generation_unit_id') == unit_id for o in owned_objects(context.scene, run_id)):
        raise ValueError('Generated geometry is missing; review was not recorded.')
    return item


def review_unit(context, props, base_dir, unit_id, run_id, state, reason=None, note=None):
    """Append first; only the selected current result changes after a successful write."""
    item = reviewable_unit(context, props, unit_id, run_id)
    current = SemanticReview(item.unit_id, item.review_state, item.reject_reason or None,
                             item.review_note or None, item.reviewed_at or None, item.review_id or None)
    review, event = record_review(review_log_path(base_dir), json.loads(item.snapshot_json),
                                  current, item.status, state, reason, note)
    item.review_state = review.review_state
    item.reject_reason, item.review_note = review.reject_reason or '', review.note or ''
    item.reviewed_at, item.review_id = review.reviewed_at, review.review_id
    return event


def set_guides_visible(props, context):
    # View-layer visibility only: no render flags, geometry, transforms or custom properties.
    if props.target_collection:
        for obj in props.target_collection.objects:
            if obj.get(OWNER) != TOOL and obj.name in context.view_layer.objects:
                obj.hide_set(not props.show_guides)