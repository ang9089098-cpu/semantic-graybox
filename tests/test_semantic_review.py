"""Human-review model regression tests; never use real research output folders."""
import unittest
import json
import tempfile
from pathlib import Path
from unittest.mock import patch
from generation.review_log import record_review, review_log_path
from generation.semantic_review import SemanticReview, request_snapshot, review_event
from generation.pipeline import GenerationQueue
from generation.prompt_builder import build_prompt
from tests.test_generation_batch import bed_blueprint


def example_snapshot():
    queue = GenerationQueue(bed_blueprint(), 'rococo', do_import=False)
    unit = queue.batch.results[0]
    return request_snapshot(unit.request, batch_id=queue.batch.run_id,
        unit_kind=unit.kind, entity_type=queue.entity, generator='cube3d',
        placement=unit.placement, output_path='fixture/output.obj',
        final_prompt=build_prompt(unit.request))


class TestSemanticReviewModel(unittest.TestCase):
    def test_completed_unit_starts_unreviewed(self):
        unit = GenerationQueue(bed_blueprint(), do_import=False).batch.results[0]
        unit.status = 'DONE'
        self.assertEqual(unit.review.review_state, 'UNREVIEWED')

    def test_accept_independent_of_execution_and_preservation(self):
        unit = GenerationQueue(bed_blueprint(), do_import=False).batch.results[0]
        unit.status = 'DONE'
        unit.review = unit.review.decide('ACCEPTED')
        self.assertEqual(unit.status, 'DONE')
        unit.status = 'KEPT'
        unit.review = unit.review.decide('REJECTED', 'WHOLE_OBJECT')
        self.assertEqual(unit.status, 'KEPT')
        self.assertEqual(unit.review.review_state, 'REJECTED')

    def test_reject_requires_controlled_reason(self):
        for reason in (None, '', 'SOMETHING_NEW'):
            with self.assertRaises(ValueError):
                SemanticReview('Master_Leg').decide('REJECTED', reason)
        self.assertEqual(SemanticReview('Master_Leg').decide('REJECTED','WRONG_PART').reject_reason, 'WRONG_PART')

    def test_other_preserves_optional_note_accept_clears_it(self):
        review = SemanticReview('Master_Leg').decide('REJECTED','OTHER','  curved in the wrong direction  ')
        self.assertEqual(review.note, 'curved in the wrong direction')
        self.assertIsNone(review.decide('ACCEPTED').note)
        self.assertIsNone(SemanticReview('Master_Leg').decide('REJECTED','OTHER').note)

    def test_event_has_request_identity_and_actual_prompt(self):
        snapshot = example_snapshot()
        review, event = review_event(snapshot, SemanticReview('Master_Leg'), 'DONE', 'ACCEPTED')
        self.assertEqual(event['final_prompt'], 'A rococo carved furniture leg for a bed')
        self.assertEqual(event['generation_unit_id'], 'Master_Leg')
        self.assertEqual(event['source_group'], 'Leg')
        self.assertEqual(event['schema_version'], '0.3.1')
        self.assertEqual(len(event['source_guide_names']), 4)
        self.assertIsNone(event['source_guide_name'])
        self.assertNotIn('review_id', snapshot)
        self.assertEqual(event['review_id'], review.review_id)

    def test_pending_generating_error_and_wrong_identity_cannot_review(self):
        for status in ('PENDING','GENERATING','ERROR'):
            with self.assertRaises(ValueError):
                review_event(example_snapshot(), SemanticReview('Master_Leg'), status, 'ACCEPTED')
        with self.assertRaises(ValueError):
            review_event(example_snapshot(), SemanticReview('Headboard'), 'DONE', 'ACCEPTED')

    def test_changed_review_gets_new_identity_without_mutating_old(self):
        first = SemanticReview('Master_Leg').decide('ACCEPTED')
        second = first.decide('REJECTED', 'WHOLE_OBJECT')
        self.assertNotEqual(first.review_id, second.review_id)
        self.assertEqual(first.review_state, 'ACCEPTED')
        self.assertEqual(second.review_state, 'REJECTED')

    def test_append_preserves_earlier_event_and_changes_get_new_ids(self):
        with tempfile.TemporaryDirectory() as directory:
            path = review_log_path(directory)
            initial = SemanticReview('Master_Leg')
            first, _ = record_review(path, example_snapshot(), initial, 'DONE', 'ACCEPTED')
            original_bytes = path.read_bytes()
            second, _ = record_review(path, example_snapshot(), first, 'KEPT', 'REJECTED', 'OTHER', '의미 검토\n메모')
            self.assertTrue(path.read_bytes().startswith(original_bytes))
            rows = [json.loads(line) for line in path.read_text(encoding='utf-8').splitlines()]
            self.assertEqual(len(rows), 2)
            self.assertNotEqual(rows[0]['review_id'], rows[1]['review_id'])
            self.assertEqual(rows[0]['semantic_review'], 'ACCEPTED')
            self.assertEqual(rows[1]['review_note'], '의미 검토\n메모')
            self.assertEqual(second.review_state, 'REJECTED')

    def test_failed_log_does_not_change_current_review(self):
        original = SemanticReview('Master_Leg').decide('ACCEPTED')
        with patch('generation.review_log.append_review_event', side_effect=OSError('disk unavailable')):
            with self.assertRaises(OSError):
                record_review(Path('unused'), example_snapshot(), original, 'DONE', 'REJECTED', 'WRONG_PART')
        self.assertEqual(original.review_state, 'ACCEPTED')

    def test_default_log_location(self):
        self.assertEqual(review_log_path('project'), Path('project/Generated/semantic_review/semantic_reviews.jsonl'))