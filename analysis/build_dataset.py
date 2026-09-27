"""Build/verify the 144-slot dataset from public repository exports; stdlib only."""
import argparse
import csv
import io
import json
import math
from collections import Counter
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SYSTEMS = {'cursor', 'devin', 'gpt-5.4', 'qwen2.5-coder-7b-instruct'}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def read(path):
    return json.loads((ROOT/path).read_text(encoding='utf-8-sig'))


def indexed(rows, key):
    result = {r[key]: r for r in rows}
    require(len(result) == len(rows), f'Duplicate {key}')
    return result


def build():
    selected, attempts = [], []
    for tier in range(1, 5):
        batch = read(f'data/L{tier}/selected_runs.json')
        require(len(batch) == 36, f'L{tier} selected count')
        for row in batch:
            require(row['task_id'].startswith(f'L{tier}-'), 'Tier mismatch')
            selected.append(row)
        attempts.extend(read(f'data/L{tier}/all_attempts.json'))
    selected.sort(key=lambda r: r['global_position'])
    runs = indexed(selected, 'run_id')
    attempt_index = indexed(attempts, 'run_id')
    schedule = indexed(read('benchmark/config/run_schedule.main.json')['entries'], 'global_position')
    original = indexed(read('data/evaluation-review/original_scores.json')['rows'], 'run_id')
    review_file = read('data/evaluation-review/reviewed_scores.json')
    reviewed = indexed(review_file['rows'], 'run_id')
    selection = read('data/evaluation-review/selection.json')
    require(len(runs) == 144 and len(attempts) == 155, 'Unexpected population')
    require(set(runs) == set(original) == set(reviewed), 'Review join coverage')
    require([r['global_position'] for r in selected] == list(range(1, 145)), 'Schedule coverage')
    require(len({(r['task_id'], r['system_id'], r['repetition']) for r in selected}) == 144, 'Duplicate slots')
    require({a['run_id'] for a in attempts if a['selected']} == set(runs), 'Attempt selection differs')
    excluded = {a['run_id'] for a in attempts if not a['selected']}
    require(excluded == {a['run_id'] for a in selection['excluded_attempts']}, 'Exclusion mismatch')
    for a in attempts:
        target = runs[a['selected_run_id']]
        require(a['global_position'] == target['global_position'], 'Replacement slot mismatch')
        require(a['validity_status'] == ('valid' if a['selected'] else 'invalid'), 'Analytical validity mismatch')
    rows = []
    for r in selected:
        rid = r['run_id']
        o, v = original[rid], reviewed[rid]
        s = schedule[r['global_position']]
        for key in ('task_id', 'system_id', 'repetition', 'order_position'):
            require(r[key] == s[key], f'{rid}: schedule {key}')
        require(r['validity_status'] == 'valid' and r['system_id'] in SYSTEMS, rid)
        require(o['task'] == v['task'] == r['task_id'] and o['system'] == v['system'] == r['system_id'], 'Review identity')
        require(o['repetition'] == r['repetition'] and o['attempt'] == r['attempt'], 'Attempt identity')
        require(r['stop_reason'] == o['stopping_reason'] == v['stopping_reason'], 'Stop mismatch')
        require(r['stop_reason'] in ('submitted', 'protocol_no_progress_limit'), 'Unexpected stopping reason')
        submitted = r['stop_reason'] == 'submitted'
        c = r['clarification']
        for key in ('requests', 'authorized_requests', 'responses'):
            require(type(c[key]) is int and c[key] >= 0, f'{rid}: clarification {key}')
        require(c['authorized_requests'] <= c['requests'] and c['responses'] <= c['authorized_requests'], 'Clarification counts')
        require(c['opportunity'] == (r['task_id'] == 'L2-02'), 'Clarification opportunity')
        tier = s['tier']
        eligible = tier >= 3
        require(r['results']['robustness_eligible'] == eligible, 'Robustness population')
        row = dict(global_position=r['global_position'], run_id=rid, task_id=r['task_id'], tier=tier,
                   system_id=r['system_id'], repetition=r['repetition'], attempt=r['attempt'],
                   order_position=r['order_position'], validity_status=r['validity_status'],
                   original_lifecycle_state=r['lifecycle_state'], stop_reason=r['stop_reason'],
                   normal_submission=int(submitted), started_at=r['timing']['started_at'],
                   ended_at=r['timing']['ended_at'], elapsed_seconds=r['timing']['elapsed_seconds'],
                   original_success=int(o['success']), reviewed_success=int(v['reviewed_success']),
                   review_version=review_file['version'])
        require(type(row['elapsed_seconds']) in (int, float) and math.isfinite(row['elapsed_seconds']) and row['elapsed_seconds'] >= 0, 'Invalid elapsed time')
        start, end = [datetime.fromisoformat(row[k].replace('Z', '+00:00')) for k in ('started_at', 'ended_at')]
        require(start.tzinfo is not None and end.tzinfo is not None and end >= start, 'Invalid timestamps')
        for group, detailkey, resultkey in [('functional', 'tests', 'functional_tests'), ('architecture', 'checks', 'architecture_checks')]:
            detail = indexed(r[detailkey], 'id')
            active = {k: x['passed'] for k, x in detail.items() if x['applicable']}
            require(all(type(x) is bool for x in active.values()) and active == o[group], 'Original check mismatch')
            recorded = r['results'][resultkey]
            require(recorded['passed'] == sum(active.values()) and recorded['applicable'] == len(active), 'Recorded check counts')
            require(math.isclose(recorded['proportion'], recorded['passed']/recorded['applicable']), 'Recorded proportion')
            for version, counts in [('original', v['original_'+group]), ('reviewed', v[group])]:
                require(type(counts['passed']) is int and type(counts['applicable']) is int and 0 <= counts['passed'] <= counts['applicable'] and counts['applicable'] > 0, 'Invalid check counts')
                if version == 'original':
                    require(counts['passed'] == recorded['passed'] and counts['applicable'] == recorded['applicable'], 'Review original mismatch')
                for key in ('passed', 'applicable'):
                    row[f'{version}_{group}_{key}'] = counts[key]
                row[f'{version}_{group}_proportion'] = counts['passed']/counts['applicable']
                if version == 'reviewed' and 'reviewed_results' in r:
                    require(all(r['reviewed_results'][resultkey][k] == counts[k] for k in ('passed', 'applicable')), 'Embedded reviewed counts')
        for version in ('original', 'reviewed'):
            success = submitted and all(row[f'{version}_{g}_passed'] == row[f'{version}_{g}_applicable'] for g in ('functional', 'architecture'))
            require(row[version+'_success'] == int(success), f'{rid}: success formula')
        require(o['success'] == v['original_success'] == r['results']['success'], 'Original success mismatch')
        require(r['lifecycle_state'] == ('successful' if o['success'] else 'unsuccessful'), 'Original lifecycle')
        if 'reviewed_results' in r:
            require(r['reviewed_results']['success'] == v['reviewed_success'] and r['reviewed_results']['version'] == review_file['version'], 'Embedded review version/outcome')
        row.update(clarification_opportunity=int(c['opportunity']), clarification_requests=c['requests'],
                   clarification_authorized_requests=c['authorized_requests'], clarification_responses=c['responses'],
                   robustness_eligible=int(eligible),
                   original_autonomous_success=int(o['success'] and c['responses'] == 0) if eligible else None,
                   reviewed_autonomous_success=int(v['reviewed_success'] and c['responses'] == 0) if eligible else None)
        require(r['results']['autonomous_success'] == (bool(row['original_autonomous_success']) if eligible else None), 'Original autonomous success')
        for key, value in r['usage'].items():
            row['usage_'+key] = value
        for key in ('input_tokens', 'output_tokens', 'total_tokens'):
            value = r['usage'][key]
            require(value is None or (type(value) is int and value >= 0), 'Invalid token count')
        u = r['usage']
        if all(u[k] is not None for k in ('input_tokens', 'output_tokens', 'total_tokens')):
            require(u['input_tokens']+u['output_tokens'] == u['total_tokens'], 'Token sum')
        row.update(r['system'])
        row['start_commit'] = r['start_commit']
        row['source_selected_runs'] = f'data/L{tier}/selected_runs.json'
        rows.append(row)
    by_system, by_tier, by_task = [dict(sorted(Counter(r[key] for r in rows).items())) for key in ('system_id', 'tier', 'task_id')]
    require(set(by_system.values()) == {36} and len(by_system) == 4, 'System denominator')
    require(set(by_tier.values()) == {36} and len(by_tier) == 4, 'Tier denominator')
    require(set(by_task.values()) == {12} and len(by_task) == 12, 'Task denominator')
    require(set(Counter((r['system_id'], r['tier']) for r in rows).values()) == {9}, 'System-tier denominator')
    stops = dict(sorted(Counter(r['stop_reason'] for r in rows).items()))
    require(stops == selection['stopping_counts'], 'Stopping totals')
    report = dict(status='passed', scope='Dataset assembly and consistency validation only; no comparative statistics or figures.',
                  selected_rows=len(rows), unique_slots=len(rows), retained_attempts=len(attempts), excluded_attempts=len(excluded),
                  review_version=review_file['version'], by_system=by_system, by_tier=by_tier, by_task=by_task,
                  stopping_counts=stops, clarification_opportunity_rows=sum(r['clarification_opportunity'] for r in rows),
                  robustness_eligible_rows=sum(r['robustness_eligible'] for r in rows),
                  missing_cells={k: sum(r[k] is None for r in rows) for k in rows[0] if any(r[k] is None for r in rows)},
                  checks=['144 unique scheduled slots; all four tiers', '155 indexed attempts; 11 exclusions; selected replacement links',
                          'Exact run_id join to original and reviewed scoring', 'Individual original checks, counts and proportions reconcile',
                          'Normal submission and all-checks-pass gate for both scoring versions', 'Published embedded review reconciles',
                          'Timing order, nonnegative elapsed and token counts', 'Clarification opportunity and robustness eligibility',
                          'Missing values preserved; no imputation'],
                  limitations=['Source evidence coverage is unchanged by these checks.', 'Elapsed time is the recorded duration, not recomputed from rounded timestamps.',
                               'Usage is not available comparably across interfaces; null is not zero.',
                               'Partial native transcripts and unknown permission counts are not reconstructed.'])
    buffer = io.StringIO(newline='')
    writer = csv.DictWriter(buffer, fieldnames=list(rows[0]), lineterminator='\n')
    writer.writeheader()
    writer.writerows(rows)
    return {'analysis_dataset.csv': buffer.getvalue(), 'validation_summary.json': json.dumps(report, ensure_ascii=False, indent=2)+'\n'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true', help='Verify committed outputs without writing')
    args = parser.parse_args()
    output = ROOT/'data/main'
    expected = build()
    if args.check:
        for name, content in expected.items():
            require((output/name).read_bytes() == content.encode('utf-8'), f'{name} differs: run build_dataset.py')
    else:
        output.mkdir(parents=True, exist_ok=True)
        for name, content in expected.items():
            (output/name).write_bytes(content.encode('utf-8'))
    print('PASS: 144 selected slots, 155 attempts, 11 exclusions; original/reviewed scores reconciled.')


if __name__ == '__main__':
    main()
