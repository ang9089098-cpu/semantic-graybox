"""Disposable v0.3 GUI review with mock generation; no user scene is opened."""
import json
import sys
import threading
import time
from pathlib import Path
import bpy
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tests.blender_batch_workflow_test import setup_bed, snapshot, verify_outputs
from blender_ui import workflow
from generation.generator_adapters.cube3d_adapter import Cube3DAdapter
from generation.generator_adapters.base import GenerationResult
from generation import blender_import

bpy.ops.wm.read_factory_settings(use_empty=True)
p, coll = setup_bed()
p.style_prompt = 'rococo'
bpy.ops.semantic_graybox.analyze()
p.show_units = True
p.show_advanced = False
guides = list(coll.objects)
saved = snapshot(guides)
main_thread = threading.get_ident()
original_generate = Cube3DAdapter.generate
original_placer = blender_import.place_master_instances
calls = []
def fake(adapter, request):
    assert threading.get_ident() != main_thread
    time.sleep(1.5)
    calls.append((request.master_id, adapter.config.output_dir))
    path = Path(adapter.config.output_dir, 'output.obj')
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text('v 0 0 0\nv 1 0 0\nv 0 1 0\nf 1 2 3\n')
    return GenerationResult(True, request.master_id, output_path=str(path))
def place(*args):
    assert threading.get_ident() == main_thread
    return original_placer(*args)
Cube3DAdapter.generate = fake
blender_import.place_master_instances = place
def configure_view():
    if bpy.context.screen is None:
        return .25
    for area in bpy.context.screen.areas:
        if area.type == 'VIEW_3D':
            area.spaces.active.show_region_ui = True
            area.spaces.active.region_3d.view_distance = 5
            try:
                area.spaces.active.region_active_panel_category = 'Semantic AI'
            except AttributeError:
                pass
    return None
bpy.app.timers.register(configure_view, first_interval=.5)
preview_dir = Path(__file__).resolve().parents[1] / 'Generated' / 'v03_manual'
preview_dir.mkdir(parents=True, exist_ok=True)
bpy.ops.wm.save_as_mainfile(filepath=str(preview_dir / 'v03_manual_preview.blend'))
def verify_async():
    if not p.result_run or p.queue_running:
        return .25
    assert (p.completed,p.failed,p.result_total) == (4,0,4)
    assert len(calls) == 4 and len({c[1] for c in calls}) == 4
    assert snapshot(guides) == saved
    verify_outputs(p, guides)
    Cube3DAdapter.generate = original_generate
    blender_import.place_master_instances = original_placer
    (preview_dir / 'async_report.json').write_text(json.dumps({
        'result':'PASS','completed':p.completed,'failed':p.failed,'instances':p.result_instances,
        'worker_generate':True,'main_thread_import':True,'calls':calls},indent=2))
    print('GUI ASYNC BED QUEUE: PASS', flush=True)
    return None
bpy.app.timers.register(verify_async, first_interval=.25)