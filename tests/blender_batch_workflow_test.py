"""Blender 5.2 Bed queue smoke; --real runs the unchanged external Cube3D runtime."""
import json
import os
import sys
import tempfile
import threading
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
from generation import blender_import


def setup_bed():
    blender_ui.register()
    coll = bpy.data.collections.new('Bed')
    bpy.context.scene.collection.children.link(coll)
    parts = [('Headboard', (1.6,.12,.8), (0,-1,.9)),
             ('LeftSideFrame', (.12,2,.2), (-.8,0,.5)),
             ('RightSideFrame', (.12,2,.2), (.8,0,.5))]
    parts += [('Leg.%03d' % (i+1), (.12,.12,.5), loc)
              for i, loc in enumerate([(-.8,-.9,.25),(.8,-.9,.25),(-.8,.9,.25),(.8,.9,.25)])]
    for name, dims, loc in parts:
        mesh = bpy.data.meshes.new(name)
        bm = bmesh.new()
        bmesh.ops.create_cube(bm, size=1)
        for v in bm.verts:
            v.co.x *= dims[0]
            v.co.y *= dims[1]
            v.co.z *= dims[2]
        bm.to_mesh(mesh)
        bm.free()
        obj = bpy.data.objects.new(name, mesh)
        coll.objects.link(obj)
        obj.location = loc  # Applied geometry; object scale is 1:1:1.
    bpy.context.view_layer.update()
    p = bpy.context.scene.semantic_graybox
    p.target_collection = coll
    p.style_prompt = 'rococo'
    return p, coll


def snapshot(guides):
    bpy.context.view_layer.update()
    return [(o.name, tuple(v for row in o.matrix_world for v in row), o.parent,
             dict(o.items()), tuple(v.co[:] for v in o.data.vertices), o.hide_get()) for o in guides]


def verify_outputs(p, guides, expected=7):
    bpy.context.view_layer.update()
    objects = workflow.owned_objects(bpy.context.scene, p.result_run)
    assert len(objects) == expected, (len(objects), expected)
    legs = [o for o in objects if o.get('generation_unit_id') == 'Master_Leg']
    assert len(legs) == 4 and len({o.data for o in legs}) == 1
    for obj in objects:
        assert obj.get('semantic_graybox_generated') is True
        assert obj.get('source_entity') == 'Bed'
        guide = next(g for g in guides if obj.get('source_guide_name') == g.name)
        assert (obj.matrix_world.translation - guide.matrix_world.translation).length < 1e-6
    return objects


def main():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    assert bpy.app.version[:2] == (5,2)
    p, coll = setup_bed()
    guides = list(coll.objects)
    saved = snapshot(guides)
    assert bpy.ops.semantic_graybox.analyze() == {'FINISHED'}
    assert (p.entity,p.parts,p.masters,p.instances,p.gen_units) == ('Bed',7,1,4,4)
    assert snapshot(guides) == saved
    unrelated = bpy.data.objects.new('Foreign output', bpy.data.meshes.new('foreign'))
    blender_import.get_or_create_collection('Generated').objects.link(unrelated)
    main_thread = threading.get_ident()
    original_placer = blender_import.place_master_instances
    def checking_placer(*args):
        assert threading.get_ident() == main_thread
        return original_placer(*args)
    with tempfile.TemporaryDirectory(prefix='semantic_batch_') as tmp:
        cfg = Cube3DConfig('unused', 'unused', 'unused', 'unused', tmp)
        calls = []
        def fake(adapter, request):
            calls.append((request.master_id, adapter.config.output_dir))
            objfile = Path(adapter.config.output_dir, 'output.obj')
            objfile.parent.mkdir(parents=True, exist_ok=True)
            objfile.write_text('v 0 0 0\nv 1 0 0\nv 0 1 0\nf 1 2 3\n')
            return GenerationResult(True, request.master_id, output_path=str(objfile))
        with patch.object(workflow, 'runtime_config', lambda *args: cfg), \
             patch.object(Cube3DAdapter, 'generate', fake), \
             patch.object(blender_import, 'place_master_instances', checking_placer):
            assert bpy.ops.semantic_graybox.generate_all() == {'FINISHED'}
            assert (p.completed,p.failed,p.result_total) == (4,0,4)
            first = set(verify_outputs(p, guides))
            assert len(calls) == 4 and len({c[1] for c in calls}) == 4
            assert sum(c[0] == 'Master_Leg' for c in calls) == 1
            def failure(adapter, request):
                if request.master_id == 'LeftSideFrame':
                    return GenerationResult(False, request.master_id, error='fixture failure')
                return fake(adapter, request)
            with patch.object(Cube3DAdapter, 'generate', failure):
                assert bpy.ops.semantic_graybox.regenerate() == {'FINISHED'}
                assert (p.completed,p.failed) == (3,1)
                assert len(workflow.owned_objects(bpy.context.scene)) == 7
                # The old failed replacement survives; successful old units are replaced.
                remaining = first.intersection(set(bpy.context.scene.objects))
                assert len(remaining) == 1
                assert next(iter(remaining))['generation_unit_id'] == 'LeftSideFrame'
                assert p.result_instances == 7
            assert bpy.ops.semantic_graybox.regenerate() == {'FINISHED'}
            assert len(workflow.owned_objects(bpy.context.scene)) == 7
            verify_outputs(p, guides)
            assert snapshot(guides) == saved
            assert bpy.ops.semantic_graybox.clear_generated() == {'FINISHED'}
            assert not workflow.owned_objects(bpy.context.scene)
            assert unrelated.name in bpy.context.scene.objects
            assert bpy.ops.semantic_graybox.generate_all() == {'FINISHED'}
            assert bpy.ops.semantic_graybox.keep() == {'FINISHED'}
            assert all(item.status == 'KEPT' for item in p.units)
            kept = set(workflow.owned_objects(bpy.context.scene))
            assert bpy.ops.semantic_graybox.clear_generated() == {'FINISHED'}
            assert set(workflow.owned_objects(bpy.context.scene)) == kept
            assert bpy.ops.semantic_graybox.regenerate() == {'FINISHED'}
            assert len(workflow.owned_objects(bpy.context.scene)) == 14
            assert bpy.ops.semantic_graybox.clear_generated() == {'FINISHED'}
            assert set(workflow.owned_objects(bpy.context.scene)) == kept
            workflow.clear_objects(kept, guides)
            # Existing scripts can still request only the first repeated master.
            assert bpy.ops.semantic_graybox.generate() == {'FINISHED'}
            assert p.result_instances == 4 and p.result_total == 0
            assert bpy.ops.semantic_graybox.clear_generated() == {'FINISHED'}
            # A collection with no repeated parts now supports Generate All as well.
            single = bpy.data.collections.new('BedUniqueOnly')
            bpy.context.scene.collection.children.link(single)
            unique_guide = guides[0].copy()
            single.objects.link(unique_guide)
            p.target_collection = single
            assert bpy.ops.semantic_graybox.generate_all() == {'FINISHED'}
            assert (p.masters,p.gen_units,p.completed,p.failed,p.result_instances) == (0,1,1,0,1)
            assert unique_guide.name in bpy.context.scene.objects
            assert bpy.ops.semantic_graybox.clear_generated() == {'FINISHED'}
            p.target_collection = coll
            bpy.ops.semantic_graybox.analyze()
            # Partial OBJ import failure removes only the objects of that unit.
            def bad_import(path):
                bpy.ops.mesh.primitive_cube_add()
                raise RuntimeError('partial import fixture')
            existing = set(bpy.data.objects)
            with patch.object(blender_import, 'import_obj', bad_import):
                try:
                    original_placer(calls[0][1] + '/output.obj', {'master_id':'Broken','slots':[]})
                except RuntimeError:
                    pass
            assert set(bpy.data.objects) == existing
        p.show_guides = False
        assert all(o.hide_get() for o in guides)
        p.show_guides = True
        assert snapshot(guides) == saved
    if '--real' in sys.argv:
        cfg = Cube3DConfig.from_env(str(ROOT))
        assert cfg.repo_dir == r'E:\AI_Tools\Cube3D\repo'
        assert Cube3DAdapter(cfg).preflight() is None
        calls = []
        original_generate = Cube3DAdapter.generate
        def real(adapter, request):
            calls.append((request.master_id, adapter.config.output_dir))
            return original_generate(adapter, request)
        with patch.object(Cube3DAdapter, 'generate', real):
            assert bpy.ops.semantic_graybox.generate_all() == {'FINISHED'}
        assert (p.completed,p.failed,p.result_total) == (4,0,4), [(u.unit_id,u.message) for u in p.units]
        verify_outputs(p, guides)
        assert len(calls) == 4 and sum(c[0] == 'Master_Leg' for c in calls) == 1
        assert len({c[1] for c in calls}) == 4
        assert snapshot(guides) == saved
        report = {'completed':p.completed,'failed':p.failed,'instances':p.result_instances,'calls':calls,
                  'prompts':{u.unit_id:u.prompt for u in p.units}}
        report_path = Path(cfg.output_dir, 'v03_bed_e2e_report.json')
        report_path.write_text(json.dumps(report, indent=2), encoding='utf-8')
        bpy.ops.wm.save_as_mainfile(filepath=str(Path(cfg.output_dir, 'v03_bed_e2e.blend')))
        print('REAL BED CUBE3D QUEUE: PASS', str(report_path))
    blender_ui.unregister()
    blender_ui.register()
    blender_ui.unregister()
    print('UI V0.3 REGISTRATION + BED QUEUE SMOKE: PASS')


if __name__ == '__main__':
    main()