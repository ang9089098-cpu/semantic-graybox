"""Blender 5.2 artist workflow integration; optional --real generation."""
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch
import bpy
import bmesh
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import blender_ui
from blender_ui import workflow
from generation.generator_adapters.base import GenerationResult
from generation.generator_adapters.cube3d_adapter import Cube3DAdapter, Cube3DConfig
bpy.ops.wm.read_factory_settings(use_empty=True)
blender_ui.register()
p = bpy.context.scene.semantic_graybox
assert bpy.app.version[:2] == (5, 2)
assert bpy.types.SEMANTICGRAYBOX_PT_panel.bl_category == 'Semantic AI'
coll = bpy.data.collections.new('Desk')
bpy.context.scene.collection.children.link(coll)
def box(name, scale, loc):
    mesh = bpy.data.meshes.new(name)
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1)
    bm.to_mesh(mesh)
    bm.free()
    obj = bpy.data.objects.new(name, mesh)
    coll.objects.link(obj)
    obj.scale, obj.location = scale, loc
    return obj
box('Top', (2,1,.1), (0,0,1))
for i, loc in enumerate([(-.9,-.4,.5),(.9,-.4,.5),(-.9,.4,.5),(.9,.4,.5)]):
    box('Leg.%03d' % (i+1), (.08,.08,.7), loc)
bpy.context.view_layer.update()
guides = list(coll.objects)
def snapshot():
    return [(o.name, tuple(v for row in o.matrix_world for v in row), o.parent, dict(o.items()), tuple(v.co[:] for v in o.data.vertices), o.hide_get()) for o in guides]
p.target_collection = coll
p.style_prompt = 'rococo'
saved = snapshot()
assert bpy.ops.semantic_graybox.analyze() == {'FINISHED'}
assert snapshot() == saved
assert (p.entity,p.parts,p.masters,p.instances) == ('Desk',5,1,4)
assert p.generated_prompt == 'A rococo carved furniture leg for a desk'
p.style_prompt = 'walnut'
assert p.generated_prompt == 'A walnut carved furniture leg for a desk'
p.style_prompt = 'rococo'
unrelated = bpy.data.objects.new('Master_Leg_Generated_unrelated', bpy.data.meshes.new('unrelated'))
generated = bpy.data.collections.new('Generated')
bpy.context.scene.collection.children.link(generated)
generated.objects.link(unrelated)
with tempfile.TemporaryDirectory(prefix='semantic_ui_') as tmp:
    obj = Path(tmp) / 'fixture.obj'
    obj.write_text('v 0 0 0\nv 1 0 0\nv 0 1 0\nf 1 2 3\n')
    def fake(adapter, request):
        return GenerationResult(True, request.master_id, output_path=str(obj))
    with patch.object(Cube3DAdapter, 'generate', fake):
        assert bpy.ops.semantic_graybox.generate() == {'FINISHED'}
        first = set(workflow.owned_objects(bpy.context.scene))
        assert len(first) == 4 and len({o.data for o in first}) == 1
        assert p.result_instances == 4 and p.result_collection == 'Generated'
        assert snapshot() == saved
        assert bpy.ops.semantic_graybox.regenerate() == {'FINISHED'}
        assert not first.intersection(set(bpy.context.scene.objects))
        current = set(workflow.owned_objects(bpy.context.scene))
        with patch.object(Cube3DAdapter, 'generate', lambda a,r: GenerationResult(False,r.master_id,error='fixture failure')):
            try:
                bpy.ops.semantic_graybox.regenerate()
            except RuntimeError:
                pass
        assert set(workflow.owned_objects(bpy.context.scene)) == current
        assert bpy.ops.semantic_graybox.keep() == {'FINISHED'}
        assert bpy.ops.semantic_graybox.regenerate() == {'FINISHED'}
        assert len(workflow.owned_objects(bpy.context.scene)) == 8
        assert bpy.ops.semantic_graybox.clear_generated() == {'FINISHED'}
        assert set(workflow.owned_objects(bpy.context.scene)) == current
        assert unrelated.name in bpy.context.scene.objects
        assert snapshot() == saved
    # Supported Advanced options reach the existing adapter config.
    p.override_options = True
    p.resolution_base = 4.0
    p.timeout_sec = 60
    p.fast_inference = True
    p.use_bounding_box = False
    def configured(adapter, request):
        cfg = adapter.config
        assert (cfg.resolution_base, cfg.timeout_sec, cfg.fast_inference, cfg.use_bounding_box) == (4.0, 60, True, False)
        return fake(adapter, request)
    with patch.object(Cube3DAdapter, 'generate', configured):
        assert bpy.ops.semantic_graybox.generate() == {'FINISHED'}
        bpy.ops.semantic_graybox.clear_generated()
    p.override_options = False
    p.show_guides = False
    assert all(o.hide_get() for o in guides)
    p.show_guides = True
    assert snapshot() == saved
    if '--real' in sys.argv:
        cfg = Cube3DConfig.from_env(str(ROOT))
        assert cfg.repo_dir == r'E:\AI_Tools\Cube3D\repo'
        assert Cube3DAdapter(cfg).preflight() is None
        os.environ['CUBE3D_OUTPUT'] = tmp
        assert bpy.ops.semantic_graybox.generate() == {'FINISHED'}
        assert p.result_instances == 4 and Path(tmp,'output.obj').is_file()
        assert snapshot() == saved
        bpy.ops.semantic_graybox.clear_generated()
        print('REAL CUBE3D UI GENERATION: PASS')
blender_ui.unregister()
blender_ui.register()
blender_ui.unregister()
assert not hasattr(bpy.types.Scene,'semantic_graybox')
print('UI V0.2 REGISTRATION + WORKFLOW SMOKE: PASS')