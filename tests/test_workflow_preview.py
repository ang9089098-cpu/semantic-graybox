import copy
import unittest
from blender_ui.workflow import preview
from tests.test_ui_pipeline import SAMPLE_BLUEPRINT
class TestWorkflowPreview(unittest.TestCase):
    def test_matches_generation_without_mutating_source(self):
        original = copy.deepcopy(SAMPLE_BLUEPRINT)
        self.assertEqual(preview(SAMPLE_BLUEPRINT,'rococo'),'A rococo carved furniture leg for a desk')
        self.assertEqual(SAMPLE_BLUEPRINT,original)
    def test_unique_only_prompt_preview(self):
        bp = copy.deepcopy(SAMPLE_BLUEPRINT)
        bp['components']['master_parts'] = []
        self.assertEqual(preview(bp,'rococo'),'A rococo carved table top for a desk')