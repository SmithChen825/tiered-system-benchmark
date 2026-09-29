"""Validate the descriptive coding table and reproduce its aggregate counts.

Coding is an evidence-based post-collection input, not an automatic diagnosis.
Run from any directory; no model calls or private runtime archive are required.
"""
import argparse
import csv
import io
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SYSTEMS = ['cursor', 'devin', 'gpt-5.4', 'qwen2.5-coder-7b-instruct']
STAGES = ['No accepted action', 'Inspection attempts; no edit',
          'Edited and submitted; checks fail']


def render(rows):
    stream = io.StringIO(newline='')
    writer = csv.DictWriter(stream, fieldnames=list(rows[0]), lineterminator='\n')
    writer.writeheader()
    writer.writerows(rows)
    return stream.getvalue()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    with (ROOT / 'data/main/analysis_dataset.csv').open(encoding='utf-8', newline='') as f:
        selected = {r['run_id']: r for r in csv.DictReader(f)}
    with (ROOT / 'results/tables/failure_coding.csv').open(encoding='utf-8', newline='') as f:
        coding = list(csv.DictReader(f))
    plan = json.loads((ROOT / 'benchmark/config/analysis_plan.main.json').read_text(encoding='utf-8'))
    categories = plan['qualitative_failure_analysis']['categories']
    expected = {k for k, r in selected.items() if r['reviewed_success'] == '0'}
    ids = [r['run_id'] for r in coding]
    if len(ids) != len(set(ids)) or set(ids) != expected or len(ids) != 42:
        raise ValueError('Coding must cover each reviewed unsuccessful selected run exactly once')
    index = json.loads((ROOT / 'results/failure_evidence_index.json').read_text(encoding='utf-8'))
    evidence = {r['run_id']: r for r in index['runs']}
    if len(index['runs']) != 42 or set(evidence) != expected:
        raise ValueError('Evidence index does not match coding population')
    for r in coding:
        source = selected[r['run_id']]
        if (r['system'], r['task'], r['stop_reason']) != (source['system_id'], source['task_id'], source['stop_reason']):
            raise ValueError(f"Selected identity mismatch: {r['run_id']}")
        codes = r['categories'].split(';')
        if len(codes) != len(set(codes)) or not set(codes) <= set(categories) or r['stage'] not in STAGES:
            raise ValueError(f"Unknown/duplicate code or stage: {r['run_id']}")
        if source['evaluation_interface'] == 'native_ide':
            if r['accepted_actions'] or r['missing_path_errors']:
                raise ValueError('Unobservable native action/error counts must remain missing')
        else:
            if int(r['accepted_actions']) < 0 or int(r['missing_path_errors']) < 0:
                raise ValueError('Negative event count')
        for path in evidence[r['run_id']]['published_sources']:
            if not (ROOT / path).is_file():
                raise ValueError(f'Missing published source: {path}')
    counts = [dict(category=c, system=s,
                   count=sum(c in r['categories'].split(';') and r['system'] == s for r in coding),
                   unsuccessful_n=sum(r['system'] == s for r in coding))
              for c in categories for s in SYSTEMS]
    stages = [dict(stage=t, system=s,
                   count=sum(r['stage'] == t and r['system'] == s for r in coding))
              for t in STAGES for s in SYSTEMS]
    for filename, rows in [('failure_category_counts.csv', counts), ('failure_stage_counts.csv', stages)]:
        path = ROOT / 'results/tables' / filename
        content = render(rows)
        if args.check:
            if path.read_text(encoding='utf-8') != content:
                raise ValueError(f'Stale aggregate: {filename}')
        else:
            path.write_text(content, encoding='utf-8', newline='')
    print(f'Validated {len(coding)} coded runs; category/stage summaries ' + ('match.' if args.check else 'written.'))


if __name__ == '__main__':
    main()
