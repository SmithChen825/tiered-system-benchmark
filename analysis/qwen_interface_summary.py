"""Summarise the published supplementary Qwen runs without model calls."""
import csv
import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def summarise():
    with (ROOT / 'data/qwen-interface-control/selected_runs.csv').open(newline='', encoding='utf-8') as f:
        rows = list(csv.DictReader(f))
    if len(rows) != 72 or {int(r['order']) for r in rows} != set(range(1, 73)):
        raise ValueError('Expected one selected record for each of 72 planned positions')
    expected = {(f'L{tier}-{task:02d}', str(rep), arm)
                for tier in range(1, 5) for task in range(1, 4)
                for rep in range(1, 4) for arm in ('A', 'B')}
    actual = Counter((r['task'], r['repetition'], r['arm']) for r in rows)
    if set(actual) != expected or any(n != 1 for n in actual.values()):
        raise ValueError('Task, repetition and arm coverage does not match the design')
    if any(r['validity'] != 'valid' for r in rows):
        raise ValueError('Invalid record in selected-run export')
    metrics = ['success', 'accepted_read_file', 'accepted_execute_bash',
               'successful_operations', 'tool_errors', 'nonempty_final_diff', 'model_responses']
    result = {}
    for arm in ('A', 'B'):
        selected = [r for r in rows if r['arm'] == arm]
        totals = {key: sum(int(r[key]) for r in selected) for key in metrics}
        totals.update(runs=len(selected), accepted_calls=totals['accepted_read_file'] + totals['accepted_execute_bash'],
                      stops=dict(Counter(r['stop'] for r in selected)))
        result[arm] = totals
    return result

if __name__ == '__main__':
    print(json.dumps(summarise(), indent=2))
