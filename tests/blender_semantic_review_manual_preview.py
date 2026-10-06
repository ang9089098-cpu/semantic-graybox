"""Disposable GUI fixture. Synthetic judgments never enter the research log."""
import json
import sys
import tempfile
from pathlib import Path
import bpy

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tests.blender_batch_workflow_test import setup_bed, snapshot
from tests.blender_semantic_review_test import fake_generate
from generation.generator_adapters.cube3d_adapter import Cube3DAdapter, Cube3DConfig
from blender_ui import workflow

bpy.ops.wm.read_factory_settings(use_empty=True)
p, collection = setup_bed()
guides = list(collection.objects)
before = snapshot(guides)
temporary = tempfile.TemporaryDirectory(prefix='semantic_review_gui_')
test_log = Path(temporary.name, 'fixture_reviews.jsonl')
cfg = Cube3DConfig('unused', 'unused', 'unused', 'unused', temporary.name)
workflow.runtime_config = lambda *args: cfg
workflow.review_log_path = lambda *args: test_log
# Keep the mock active throughout this disposable session; no GPU launch is possible.
Cube3DAdapter.generate = fake_generate
bpy.ops.semantic_graybox.analyze()
p.show_units = True
p.show_advanced = False
report_dir = ROOT / 'Generated' / 'v031_manual'
report_dir.mkdir(parents=True, exist_ok=True)


def configure_view():
    if bpy.context.screen is None:
        return .25
    for area in bpy.context.screen.areas:
        if area.type == 'VIEW_3D':
            area.spaces.active.show_region_ui = True
            area.spaces.active.region_3d.view_distance = 5
    return None


def verify_review():
    states = {u.unit_id: (u.review_state, u.reject_reason) for u in p.result_units}
    expected = {'Headboard': ('ACCEPTED', ''), 'LeftSideFrame': ('REJECTED', 'WHOLE_OBJECT'),
                'Master_Leg': ('REJECTED', 'WRONG_PART'), 'RightSideFrame': ('UNREVIEWED', '')}
    if states != expected:
        return .5
    assert snapshot(guides) == before
    assert not p.result_kept and all(u.status == 'DONE' for u in p.result_units)
    events = [json.loads(line) for line in test_log.read_text(encoding='utf-8').splitlines()]
    assert len(events) == 3
    report = {'result': 'PASS', 'synthetic_fixture_only': True, 'states': states,
              'guides_preserved': True, 'execution_status_unchanged': True,
              'keep_independent': True, 'events': events}
    (report_dir / 'review_report.json').write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding='utf-8')
    print('GUI SEMANTIC REVIEW FIXTURE: PASS', flush=True)
    return None


bpy.app.timers.register(configure_view, first_interval=.5)
bpy.app.timers.register(verify_review, first_interval=.5)
print('GUI REVIEW READY; temporary test log:', test_log, flush=True)