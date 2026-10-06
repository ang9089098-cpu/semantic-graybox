"""Blender review regression: test judgments and logs use temporary fixtures only."""
import json
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch
import bpy

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import blender_ui
from blender_ui import workflow
from tests.blender_batch_workflow_test import setup_bed, snapshot, verify_outputs
from generation.generator_adapters.base import GenerationResult
from generation.generator_adapters.cube3d_adapter import Cube3DAdapter, Cube3DConfig
from generation.prompt_builder import build_prompt


def fake_generate(adapter, request):
    output = Path(adapter.config.output_dir, 'output.obj')
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text('v 0 0 0\nv 1 0 0\nv 0 1 0\nf 1 2 3\n')
    return GenerationResult(True, request.master_id, output_path=str(output),
                            diagnostics={'prompt': build_prompt(request), 'fixture': True})


def main():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    assert bpy.app.version[:2] == (5, 2)
    p, collection = setup_bed()
    guides = list(collection.objects)
    original = snapshot(guides)
    with tempfile.TemporaryDirectory(prefix='semantic_review_test_') as directory:
        log = Path(directory, 'reviews.jsonl')
        cfg = Cube3DConfig('unused', 'unused', 'unused', 'unused', directory)
        with patch.object(workflow, 'runtime_config', lambda *args: cfg), \
             patch.object(Cube3DAdapter, 'generate', fake_generate), \
             patch.object(workflow, 'review_log_path', lambda *args: log):
            assert bpy.ops.semantic_graybox.generate_all() == {'FINISHED'}
            geometry = set(verify_outputs(p, guides))
            run_id = p.result_run
            units = {u.unit_id: u for u in p.result_units}
            assert len(units) == 4 and all(u.review_state == 'UNREVIEWED' for u in units.values())
            assert all(u.status == 'DONE' and u.has_geometry for u in units.values())
            assert bpy.ops.semantic_graybox.accept_unit(unit_id='Headboard', run_id=run_id) == {'FINISHED'}
            assert units['Headboard'].review_state == 'ACCEPTED'
            assert all(u.review_state == 'UNREVIEWED' for k, u in units.items() if k != 'Headboard')
            assert not p.result_kept and all(not o.get(workflow.KEPT) for o in geometry)
            assert bpy.ops.semantic_graybox.reject_unit(unit_id='LeftSideFrame', run_id=run_id, reason='WHOLE_OBJECT') == {'FINISHED'}
            assert bpy.ops.semantic_graybox.reject_unit(unit_id='Master_Leg', run_id=run_id, reason='WRONG_PART') == {'FINISHED'}
            assert geometry == set(workflow.owned_objects(bpy.context.scene))
            assert snapshot(guides) == original
            rows = [json.loads(line) for line in log.read_text(encoding='utf-8').splitlines()]
            assert len(rows) == 3
            assert rows[1]['reject_reason'] == 'WHOLE_OBJECT'
            assert rows[2]['source_guide_names'] == ['Leg.001', 'Leg.002', 'Leg.003', 'Leg.004']
            assert rows[2]['final_prompt'] == 'A rococo carved furniture leg for a bed'
            # Edits and Analyze change the plan, never the generated snapshot/review.
            p.style_prompt = 'walnut'
            bpy.ops.semantic_graybox.analyze()
            assert units['Headboard'].review_state == 'ACCEPTED'
            assert bpy.ops.semantic_graybox.reject_unit(unit_id='Headboard', run_id=run_id, reason='OTHER', note='fixture note') == {'FINISHED'}
            rows = [json.loads(line) for line in log.read_text(encoding='utf-8').splitlines()]
            assert rows[-1]['style_prompt'] == 'rococo'
            assert rows[-1]['final_prompt'] == rows[0]['final_prompt']
            assert rows[-1]['review_id'] != rows[0]['review_id']
            assert rows[-1]['review_note'] == 'fixture note'
            # Failed persistence leaves review, execution, geometry unchanged.
            state_before = (units['Headboard'].review_state, units['Headboard'].review_id, p.status)
            with patch('generation.review_log.append_review_event', side_effect=OSError('fixture disk failure')):
                try:
                    bpy.ops.semantic_graybox.accept_unit(unit_id='Headboard', run_id=run_id)
                except RuntimeError as exc:
                    assert 'fixture disk failure' in str(exc)
                else:
                    raise AssertionError('Review write failure must be reported')
            assert state_before == (units['Headboard'].review_state, units['Headboard'].review_id, p.status)
            assert geometry == set(workflow.owned_objects(bpy.context.scene))
            assert bpy.ops.semantic_graybox.keep() == {'FINISHED'}
            assert all(u.status == 'KEPT' for u in p.result_units)
            assert units['Headboard'].review_state == 'REJECTED'
            assert bpy.ops.semantic_graybox.accept_unit(unit_id='Headboard', run_id=run_id) == {'FINISHED'}
            assert units['Headboard'].status == 'KEPT' and units['Headboard'].review_state == 'ACCEPTED'
            assert json.loads(log.read_text(encoding='utf-8').splitlines()[-1])['execution_status'] == 'KEPT'
            preserved = log.read_bytes()
            assert bpy.ops.semantic_graybox.clear_generated() == {'FINISHED'}
            assert geometry == set(workflow.owned_objects(bpy.context.scene))
            assert log.read_bytes() == preserved
            assert bpy.ops.semantic_graybox.regenerate() == {'FINISHED'}
            assert p.result_run != run_id
            assert all(u.review_state == 'UNREVIEWED' for u in p.result_units)
            assert len(workflow.owned_objects(bpy.context.scene)) == 14
            try:
                workflow.review_unit(bpy.context, p, str(ROOT), 'Headboard', run_id, 'ACCEPTED')
            except ValueError:
                pass
            else:
                raise AssertionError('Stale review identity accepted')
            assert bpy.ops.semantic_graybox.clear_generated() == {'FINISHED'}
            assert log.read_bytes() == preserved
            assert all(not u.has_geometry for u in p.result_units)
            workflow.clear_objects(geometry, guides)
            assert bpy.ops.semantic_graybox.generate() == {'FINISHED'}
            assert len(p.result_units) == 1 and p.result_units[0].review_state == 'UNREVIEWED'
            assert bpy.ops.semantic_graybox.accept_unit(unit_id=p.result_units[0].unit_id, run_id=p.result_run) == {'FINISHED'}
            legacy_log = log.read_bytes()
            bpy.ops.semantic_graybox.clear_generated()
            assert log.read_bytes() == legacy_log and snapshot(guides) == original
            # Failed execution has no reviewable new geometry, even if replacement retains an old mesh.
            def fail(adapter, request):
                return GenerationResult(False, request.master_id, error='fixture failure')
            with patch.object(Cube3DAdapter, 'generate', fail):
                bpy.ops.semantic_graybox.generate_all()
            assert all(u.status == 'ERROR' and not u.has_geometry for u in p.result_units)
            for status in ('PENDING', 'GENERATING', 'ERROR'):
                p.result_units[0].status = status
                try:
                    workflow.reviewable_unit(bpy.context, p, p.result_units[0].unit_id, p.result_run)
                except ValueError:
                    pass
                else:
                    raise AssertionError('Non-completed unit was reviewable')
            assert log.read_bytes() == legacy_log
    blender_ui.unregister()
    blender_ui.register()
    blender_ui.unregister()
    print('UI V0.3.1 SEMANTIC REVIEW + LOG + LEGACY REGRESSION: PASS')


if __name__ == '__main__':
    main()