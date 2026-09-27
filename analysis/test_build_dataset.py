"""Regression checks for joins/selection; no agent or network execution."""
import copy
import unittest
from unittest.mock import patch
import build_dataset


class DatasetChecks(unittest.TestCase):
    def reject(self, path, mutate, message):
        original_read = build_dataset.read
        altered = copy.deepcopy(original_read(path))
        mutate(altered)
        with patch.object(build_dataset, 'read', side_effect=lambda p: altered if p == path else original_read(p)):
            with self.assertRaisesRegex(ValueError, message):
                build_dataset.build()

    def test_duplicate_slot_rejected(self):
        self.reject('data/L1/selected_runs.json', lambda rows: rows.__setitem__(1, rows[0]), 'Duplicate run_id')

    def test_missing_review_join_rejected(self):
        self.reject('data/evaluation-review/reviewed_scores.json', lambda data: data['rows'].pop(), 'Review join coverage')

    def test_invalid_attempt_cannot_be_selected(self):
        self.reject('data/L1/all_attempts.json', lambda rows: rows[0].update(selected=True), 'Attempt selection differs')

    def test_limit_stop_cannot_be_success(self):
        def change(data):
            row = next(r for r in data['rows'] if r['stopping_reason'] == 'protocol_no_progress_limit')
            row['reviewed_success'] = True
            for key in ('functional', 'architecture'):
                row[key]['passed'] = row[key]['applicable']
        self.reject('data/evaluation-review/reviewed_scores.json', change, 'success formula')


if __name__ == '__main__':
    unittest.main()
