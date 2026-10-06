"""Thin artist workflow panel for Blender 5.2."""
import os
import sys
import textwrap
import bpy
from bpy.props import BoolProperty, CollectionProperty, EnumProperty, FloatProperty, IntProperty, PointerProperty, StringProperty
from bpy.types import Operator, Panel, PropertyGroup
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)
from blender_ui import workflow
from generation.semantic_review import REVIEW_STATES, REJECT_REASONS

class SemanticGrayboxUnit(PropertyGroup):
    unit_id: StringProperty()
    kind: StringProperty()
    status: StringProperty(default="PENDING")
    instance_count: IntProperty(default=1)
    message: StringProperty()
    prompt: StringProperty()
    run_id: StringProperty()
    snapshot_json: StringProperty(options={"HIDDEN"})
    has_geometry: BoolProperty(default=False)
    review_state: EnumProperty(items=[(s, s, s) for s in REVIEW_STATES], default="UNREVIEWED")
    reject_reason: StringProperty()
    review_note: StringProperty()
    reviewed_at: StringProperty()
    review_id: StringProperty()

class SemanticGrayboxProps(PropertyGroup):
    target_collection: PointerProperty(name="Target Collection", type=bpy.types.Collection, update=workflow.reset_analysis)
    style_prompt: StringProperty(name="Style / Intent", update=workflow.refresh_preview)
    generator: EnumProperty(name="Generator", items=[("cube3d", "Cube3D", "Roblox Cube3D v0.5")], default="cube3d")
    blueprint_json: StringProperty(options={"HIDDEN"})
    generated_prompt: StringProperty(default="Analyze Graybox to preview the prompt.")
    entity: StringProperty(default="Not analyzed")
    parts: IntProperty()
    masters: IntProperty()
    instances: IntProperty()
    gen_units: IntProperty()
    units: CollectionProperty(type=SemanticGrayboxUnit)
    result_units: CollectionProperty(type=SemanticGrayboxUnit)
    show_units: BoolProperty(name="Generation Units", default=False)
    queue_running: BoolProperty(default=False, options={"SKIP_SAVE"})
    completed: IntProperty()
    failed: IntProperty()
    result_total: IntProperty()
    status: StringProperty(default="Choose Target Collection and Analyze Graybox.")
    result_run: StringProperty()
    result_master: StringProperty()
    result_instances: IntProperty()
    result_collection: StringProperty()
    result_kept: BoolProperty()
    show_guides: BoolProperty(name="Show Graybox Guides", default=True, update=workflow.set_guides_visible)
    show_advanced: BoolProperty(name="Advanced", default=False)
    override_options: BoolProperty(name="Override runtime options", default=False)
    resolution_base: FloatProperty(name="Resolution Base", default=8.0, min=1.0)
    timeout_sec: IntProperty(name="Timeout (seconds)", default=1800, min=1)
    fast_inference: BoolProperty(name="Fast Inference", default=False)
    use_bounding_box: BoolProperty(name="Guide Ratio Conditioning", default=True)

class SEMANTICGRAYBOX_OT_analyze(Operator):
    bl_idname = "semantic_graybox.analyze"
    bl_label = "Analyze Graybox"
    def execute(self, context):
        p = context.scene.semantic_graybox
        try:
            workflow.analyze(p)
        except Exception as exc:
            p.status = str(exc)
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}
        return {"FINISHED"}

def _generate(operator, context, replace=False):
    p = context.scene.semantic_graybox
    try:
        workflow.generate(context, p, _PROJECT_ROOT, replace)
    except Exception as exc:
        p.status = str(exc).splitlines()[0]
        print("[Semantic Graybox]", exc)
        operator.report({"ERROR"}, p.status)
        return {"CANCELLED"}
    operator.report({"INFO"}, p.status)
    return {"FINISHED"}

class SEMANTICGRAYBOX_OT_generate(Operator):
    bl_idname = "semantic_graybox.generate"
    bl_label = "Generate"
    bl_options = {"REGISTER"}
    @classmethod
    def poll(cls, context):
        return workflow._ACTIVE is None
    def execute(self, context):
        return _generate(self, context)

class SEMANTICGRAYBOX_OT_generate_all(Operator):
    bl_idname = "semantic_graybox.generate_all"
    bl_label = "Generate All"
    bl_description = "Generate each unique/master part once, sequentially"
    @classmethod
    def poll(cls, context):
        return workflow._ACTIVE is None
    def execute(self, context):
        return _generate_all(self, context)

def _generate_all(operator, context, replace=False):
    p = context.scene.semantic_graybox
    try:
        outcome = workflow.generate_all(context, p, _PROJECT_ROOT, replace)
    except Exception as exc:
        p.status = str(exc).splitlines()[0]
        operator.report({"ERROR"}, p.status)
        return {"CANCELLED"}
    operator.report({"INFO"}, p.status)
    return {"FINISHED"}

class SEMANTICGRAYBOX_OT_regenerate(Operator):
    bl_idname = "semantic_graybox.regenerate"
    bl_label = "Regenerate"
    bl_description = "Replace the current unkept result only after successful generation"
    @classmethod
    def poll(cls, context):
        return workflow._ACTIVE is None and bool(context.scene.semantic_graybox.result_run)
    def execute(self, context):
        if context.scene.semantic_graybox.result_total:
            return _generate_all(self, context, True)
        return _generate(self, context, True)

class SEMANTICGRAYBOX_OT_keep(Operator):
    bl_idname = "semantic_graybox.keep"
    bl_label = "Keep"
    bl_description = "Preserve this result during Regenerate and Clear Generated"
    @classmethod
    def poll(cls, context):
        p = context.scene.semantic_graybox
        return workflow._ACTIVE is None and bool(p.result_run) and not p.result_kept
    def execute(self, context):
        p = context.scene.semantic_graybox
        workflow.keep_result(context, p)
        return {"FINISHED"}

class SEMANTICGRAYBOX_OT_clear(Operator):
    bl_idname = "semantic_graybox.clear_generated"
    bl_label = "Clear Generated"
    bl_description = "Remove unkept tool outputs; preserve source guides and kept results"
    bl_options = {"REGISTER", "UNDO"}
    @classmethod
    def poll(cls, context):
        return workflow._ACTIVE is None
    def execute(self, context):
        p = context.scene.semantic_graybox
        guides = p.target_collection.objects if p.target_collection else ()
        count = workflow.clear_objects([o for o in workflow.owned_objects(context.scene) if not o.get(workflow.KEPT)], guides)
        if not workflow.owned_objects(context.scene, p.result_run):
            workflow.clear_result(p)
            for item in p.units:
                if item.status == "DONE":
                    item.status = "PENDING"
        p.status = "Cleared {0} generated instances.".format(count)
        return {"FINISHED"}

def _review(operator, context, state, reason=None, note=None):
    try:
        workflow.review_unit(context, context.scene.semantic_graybox, _PROJECT_ROOT,
                             operator.unit_id, operator.run_id, state, reason, note)
    except Exception as exc:
        operator.report({"ERROR"}, "Review not recorded: " + str(exc))
        return {"CANCELLED"}
    operator.report({"INFO"}, operator.unit_id + ": " + state)
    return {"FINISHED"}


class SEMANTICGRAYBOX_OT_accept(Operator):
    bl_idname = "semantic_graybox.accept_unit"
    bl_label = "Accept"
    bl_description = "Mark this part semantically correct; Keep remains independent"
    unit_id: StringProperty()
    run_id: StringProperty()
    @classmethod
    def poll(cls, context):
        return workflow._ACTIVE is None
    def execute(self, context):
        return _review(self, context, "ACCEPTED")


class SEMANTICGRAYBOX_OT_reject(Operator):
    bl_idname = "semantic_graybox.reject_unit"
    bl_label = "Reject"
    bl_description = "Record a semantic failure without deleting the generated part"
    unit_id: StringProperty()
    run_id: StringProperty()
    reason: EnumProperty(name="Reason", items=[(r, r.replace('_', ' ').title(), r) for r in REJECT_REASONS], default="WRONG_PART")
    note: StringProperty(name="Note (optional)", maxlen=512)
    @classmethod
    def poll(cls, context):
        return workflow._ACTIVE is None
    def invoke(self, context, event):
        try:
            workflow.reviewable_unit(context, context.scene.semantic_graybox, self.unit_id, self.run_id)
        except Exception as exc:
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}
        return context.window_manager.invoke_props_dialog(self, width=300)
    def draw(self, context):
        self.layout.label(text=self.unit_id)
        self.layout.prop(self, "reason")
        self.layout.prop(self, "note")
    def execute(self, context):
        return _review(self, context, "REJECTED", self.reason, self.note)


def _text(layout, text, width):
    for line in textwrap.wrap(text, width=max(20, int(width / 8))) or [""]:
        layout.label(text=line)

class SEMANTICGRAYBOX_PT_panel(Panel):
    bl_label = "Semantic Graybox"
    bl_idname = "SEMANTICGRAYBOX_PT_panel"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Semantic AI"
    def draw(self, context):
        layout = self.layout
        p = context.scene.semantic_graybox
        layout.enabled = workflow._ACTIVE is None
        box = layout.box()
        box.label(text="1. Graybox")
        box.label(text="Target Collection")
        box.prop(p, "target_collection", text="")
        box.operator("semantic_graybox.analyze")
        box.label(text="Entity: " + p.entity)
        box.label(text=f"Parts: {p.parts}   Masters: {p.masters}")
        box.label(text=f"Instances: {p.instances}")
        box.label(text=f"Gen. Units: {p.gen_units}")
        box = layout.box()
        box.label(text="2. Prompt")
        box.label(text="Style / Intent")
        box.prop(p, "style_prompt", text="")
        box.label(text=f"Generation Plan: {p.gen_units} units")
        box.label(text="Prompt Preview")
        if len(p.units):
            box.label(text=p.units[0].unit_id)
        _text(box, p.generated_prompt, context.region.width - 40)
        box = layout.box()
        box.label(text="3. Generate")
        box.label(text="Generator")
        box.prop(p, "generator", text="")
        box.operator("semantic_graybox.generate_all", icon="PLAY")
        _text(box, p.status, context.region.width - 40)
        box = layout.box()
        box.label(text="4. Result")
        box.label(text=f"Completed: {p.completed} / {p.result_total}")
        box.label(text=f"Failed: {p.failed}")
        box.label(text=f"Instances: {p.result_instances}")
        _text(box, "Collection: " + (p.result_collection or "—"), context.region.width - 40)
        row = box.row(align=True)
        row.operator("semantic_graybox.keep", text="Kept" if p.result_kept else "Keep")
        row.operator("semantic_graybox.regenerate")
        box.operator("semantic_graybox.clear_generated")
        box.prop(p, "show_guides")
        layout.prop(p, "show_units", icon="TRIA_DOWN" if p.show_units else "TRIA_RIGHT", emboss=False)
        if p.show_units:
            box = layout.box()
            for item in (p.result_units if len(p.result_units) else p.units):
                icon = {"DONE": "CHECKMARK", "KEPT": "LOCKED", "ERROR": "ERROR", "GENERATING": "TIME"}.get(item.status, "RADIOBUT_OFF")
                card = box.column(align=True)
                card.label(text=f"{item.unit_id} ×{item.instance_count}", icon=icon)
                card.label(text="Execution: " + item.status)
                card.label(text="Review: " + item.review_state)
                if item.review_state == "REJECTED":
                    _text(card, item.reject_reason, context.region.width - 40)
                if item.has_geometry and item.status in ("DONE", "KEPT"):
                    row = card.row(align=True)
                    for op in ("accept_unit", "reject_unit"):
                        button = row.operator("semantic_graybox." + op)
                        button.unit_id, button.run_id = item.unit_id, item.run_id
                card.separator()
                if item.message and item.status == "ERROR":
                    _text(box, item.message, context.region.width - 40)
        layout.prop(p, "show_advanced", icon="TRIA_DOWN" if p.show_advanced else "TRIA_RIGHT", emboss=False)
        if p.show_advanced:
            box = layout.box()
            for item in p.units:
                box.label(text=item.unit_id)
                _text(box, item.prompt, context.region.width - 40)
            box.prop(p, "override_options")
            col = box.column()
            col.enabled = p.override_options
            for name in ("resolution_base", "timeout_sec", "fast_inference", "use_bounding_box"):
                col.prop(p, name)

_CLASSES = (SemanticGrayboxUnit, SemanticGrayboxProps, SEMANTICGRAYBOX_OT_analyze, SEMANTICGRAYBOX_OT_generate, SEMANTICGRAYBOX_OT_generate_all, SEMANTICGRAYBOX_OT_regenerate, SEMANTICGRAYBOX_OT_keep, SEMANTICGRAYBOX_OT_clear, SEMANTICGRAYBOX_OT_accept, SEMANTICGRAYBOX_OT_reject, SEMANTICGRAYBOX_PT_panel)
def register():
    for cls in _CLASSES:
        bpy.utils.register_class(cls)
    bpy.types.Scene.semantic_graybox = PointerProperty(type=SemanticGrayboxProps)
def unregister():
    workflow.assert_idle()
    del bpy.types.Scene.semantic_graybox
    for cls in reversed(_CLASSES):
        bpy.utils.unregister_class(cls)