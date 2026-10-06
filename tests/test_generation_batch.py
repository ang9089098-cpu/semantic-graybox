"""Production multi-part queue regression tests; no GPU or bpy required."""
import copy
import unittest
from tests.test_ui_pipeline import SAMPLE_BLUEPRINT
from generation.request import requests_from_blueprint
from generation.prompt_builder import build_prompt


def bed_blueprint():
    bp = copy.deepcopy(SAMPLE_BLUEPRINT)
    bp['entity_type'] = 'Bed'
    bp['components']['unique_parts'] = [
        {'name': name, 'transform': {'location': [i, 0, 1]},
         'anchor_points': {'dimensions': [1, .2, .5]}}
        for i, name in enumerate(('Headboard', 'SideFrame_L', 'SideFrame_R'))]
    return bp


class TestGenerationPlan(unittest.TestCase):
    def test_bed_four_units_seven_slots_without_mutation(self):
        bp = bed_blueprint()
        before = copy.deepcopy(bp)
        requests = requests_from_blueprint(bp)
        self.assertEqual(len(requests), 4)
        self.assertEqual(sum(r.instance_count for r in requests), 7)
        self.assertEqual(len([r for r in requests if r.master_id == 'Master_Leg']), 1)
        self.assertEqual(bp, before)

    def test_unique_only_and_master_only(self):
        bp = bed_blueprint()
        bp['components']['master_parts'] = []
        bp['components']['unique_parts'] = bp['components']['unique_parts'][:1]
        self.assertEqual(len(requests_from_blueprint(bp)), 1)
        bp['components']['master_parts'] = SAMPLE_BLUEPRINT['components']['master_parts']
        bp['components']['unique_parts'] = []
        self.assertEqual(len(requests_from_blueprint(bp)), 1)

    def test_bed_prompts_use_shared_style_and_unit_context(self):
        requests = requests_from_blueprint(bed_blueprint())
        for request in requests:
            request.style_prompt = 'rococo'
        prompts = {r.master_id: build_prompt(r) for r in requests}
        self.assertEqual(prompts['Master_Leg'], 'A rococo carved furniture leg for a bed')
        self.assertIn('headboard for a bed', prompts['Headboard'])
        self.assertIn('side frame for a bed', prompts['SideFrame_L'])


from pathlib import Path
import tempfile
from generation.pipeline import GenerationQueue, run_generation_batch
from generation.generator_adapters.cube3d_adapter import Cube3DConfig
from generation.generator_adapters.base import GenerationResult


class TestSequentialQueue(unittest.TestCase):
    def run_batch(self, fail=None, placer=None):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = Cube3DConfig('python', 'repo', 'gpt', 'shape', tmp)
            calls = []
            class Adapter:
                def __init__(self, config):
                    self.config = config
                def generate(self, request):
                    calls.append((request.master_id, self.config.output_dir))
                    if request.master_id == fail:
                        raise RuntimeError('fixture failure')
                    path = Path(self.config.output_dir, 'output.obj')
                    path.parent.mkdir(parents=True)
                    path.write_text('v 0 0 0\nv 1 0 0\nv 0 1 0\nf 1 2 3\n')
                    return GenerationResult(True, request.master_id, output_path=str(path))
            result = run_generation_batch(blueprint=bed_blueprint(), config=cfg,
                adapter_factory=Adapter, do_import=placer is not None, placer=placer)
            self.assertEqual(cfg.output_dir, tmp)
            return result, calls

    def test_four_success_fifo_and_distinct_paths(self):
        result, calls = self.run_batch()
        self.assertTrue(result.success)
        self.assertEqual((result.total, result.completed, result.failed), (4,4,0))
        self.assertEqual([c[0] for c in calls], [r.master_id for r in requests_from_blueprint(bed_blueprint())])
        self.assertEqual(len({c[1] for c in calls}), 4)
        self.assertEqual(sum(c[0] == 'Master_Leg' for c in calls), 1)

    def test_failure_continues_preserving_successes(self):
        result, calls = self.run_batch(fail='SideFrame_L')
        self.assertFalse(result.success)
        self.assertTrue(result.finished)
        self.assertEqual((result.completed,result.failed,len(calls)), (3,1,4))
        self.assertEqual([u.status for u in result.results], ['DONE','DONE','ERROR','DONE'])

    def test_unique_and_master_placement_and_import_failure(self):
        placed = []
        def placer(path, placement, collection):
            if placement['master_id'] == 'SideFrame_L':
                raise RuntimeError('import failure')
            objects = [{} for _ in placement['slots']]
            placed.extend(objects)
            return objects
        result, _ = self.run_batch(placer=placer)
        self.assertEqual((result.completed, result.failed), (3,1))
        self.assertEqual(len(placed), 6)
        self.assertEqual(sum(o['generation_unit_id'] == 'Master_Leg' for o in placed), 4)
        self.assertTrue(all(o['source_entity'] == 'Bed' for o in placed))

    def test_cannot_start_second_unit_and_run_paths_are_unique(self):
        bp = bed_blueprint()
        q = GenerationQueue(bp, do_import=False)
        first = q.begin_next()
        self.assertEqual(first.status, 'GENERATING')
        with self.assertRaises(RuntimeError):
            q.begin_next()
        self.assertNotEqual(q.output_root, GenerationQueue(bp, do_import=False).output_root)

    def test_empty_and_invalid_generator(self):
        with self.assertRaises(ValueError):
            GenerationQueue({'components':{}}, do_import=False)
        with self.assertRaises(ValueError):
            GenerationQueue(bed_blueprint(), generator='nope')