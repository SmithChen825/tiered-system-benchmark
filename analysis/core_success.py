"""Core success analysis: all 144 slots; task-paired inference; no agent calls."""
import csv
import hashlib
import itertools
import json
import platform
from pathlib import Path
from statistics import NormalDist

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
SYSTEMS = ['cursor', 'devin', 'gpt-5.4', 'qwen2.5-coder-7b-instruct']


def wilson(k, n):
    z = NormalDist().inv_cdf(.975)
    p = k/n
    center = (p+z*z/(2*n))/(1+z*z/n)
    half = z*np.sqrt(p*(1-p)/n+z*z/(4*n*n))/(1+z*z/n)
    return max(0., center-half), min(1., center+half)


def exact_paired_p(differences):
    # Integer task success-count differences avoid floating-point tie ambiguity.
    d = np.asarray(differences, dtype=int)
    signs = np.array(list(itertools.product([-1, 1], repeat=len(d))))
    return float(np.mean(np.abs(signs @ d) >= abs(d.sum())))


def holm(values):
    order = np.argsort(values, kind='stable')
    corrected = np.empty(len(values))
    maximum = 0.
    for rank, index in enumerate(order):
        maximum = max(maximum, min(1., (len(values)-rank)*values[index]))
        corrected[index] = maximum
    return corrected


def write_csv(path, rows):
    with path.open('w', encoding='utf-8', newline='') as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]), lineterminator='\n')
        w.writeheader()
        w.writerows(rows)


def main():
    data = ROOT/'data/main/analysis_dataset.csv'
    plan_path = ROOT/'benchmark/config/analysis_plan.main.json'
    plan = json.loads(plan_path.read_text(encoding='utf-8-sig'))
    rows = list(csv.DictReader(data.open(encoding='utf-8', newline='')))
    assert len(rows) == len({r['run_id'] for r in rows}) == 144
    tasks = sorted({r['task_id'] for r in rows})
    assert len(tasks) == 12
    assert {r['review_version'] for r in rows} == {'public-contract-audit/2026-09-26'}
    assert len({(r['task_id'],r['system_id'],r['repetition']) for r in rows}) == 144
    assert set(r['system_id'] for r in rows) == set(SYSTEMS)
    for r in rows:
        for version in ('original', 'reviewed'):
            expected = r['stop_reason'] == 'submitted' and all(int(r[f'{version}_{g}_passed']) == int(r[f'{version}_{g}_applicable']) for g in ('functional','architecture'))
            assert int(r[version+'_success']) == int(expected)
    seed_text = plan['reproducibility']['bootstrap_random_seed']
    # The frozen string seed had no integer conversion specified. Declare it here.
    seed = int.from_bytes(hashlib.sha256(seed_text.encode('utf-8')).digest()[:8], 'big')
    rng = np.random.Generator(np.random.PCG64(seed))
    samples = rng.integers(0, 12, size=(plan['pairwise_comparisons']['bootstrap_resamples'], 12))
    tables = ROOT/'results/tables'
    tables.mkdir(parents=True, exist_ok=True)
    summaries, pairs = [], []
    for version in ('reviewed', 'original'):
        for level, groups in [('overall',['all']), ('tier',['1','2','3','4']), ('task',tasks)]:
            for group in groups:
                for system in SYSTEMS:
                    subset = [r for r in rows if r['system_id']==system and (level=='overall' or r['tier' if level=='tier' else 'task_id']==group)]
                    n = len(subset)
                    assert n == {'overall':36,'tier':9,'task':3}[level]
                    k = sum(int(r[version+'_success']) for r in subset)
                    lo, hi = wilson(k,n)
                    summaries.append(dict(scoring=version,level=level,group=group,system=system,successes=k,n=n,rate=k/n,ci_low=lo,ci_high=hi,interval='descriptive_Wilson_95'))
        counts = np.array([[sum(int(r[version+'_success']) for r in rows if r['task_id']==task and r['system_id']==system) for system in SYSTEMS] for task in tasks])
        version_pairs = []
        for a,b in plan['pairwise_comparisons']['contrasts']:
            d = counts[:,SYSTEMS.index(a)]-counts[:,SYSTEMS.index(b)]
            bootstrap = d[samples].mean(axis=1)/3
            lo,hi = np.quantile(bootstrap,[.025,.975],method='linear')
            version_pairs.append(dict(scoring=version,system_a=a,system_b=b,risk_difference=d.sum()/36,ci_low=lo,ci_high=hi,p_exact=exact_paired_p(d),tasks=12,repetitions_per_task=3,bootstrap_resamples=len(samples),permutations=4096))
        for record,p_adjusted in zip(version_pairs,holm([p['p_exact'] for p in version_pairs])):
            record['p_holm'] = float(p_adjusted)
            record['reject_holm_005'] = int(p_adjusted < .05)
        pairs.extend(version_pairs)
    write_csv(tables/'success_summaries.csv', summaries)
    write_csv(tables/'pairwise_success.csv', pairs)
    manifest = dict(source_commit='0bf95f7630e8c87e6ccb95292ed34de02296b4e1',review_version='public-contract-audit/2026-09-26',
                    dataset_sha256=hashlib.sha256(data.read_bytes()).hexdigest(),analysis_script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                    analysis_plan_sha256=hashlib.sha256(plan_path.read_bytes()).hexdigest(),python=platform.python_version(),numpy=np.__version__,
                    seed_text=seed_text,seed_integer=seed,seed_conversion='SHA256 UTF-8 string; first 8 digest bytes, unsigned big-endian',generator='NumPy PCG64',
                    task_order=tasks,bootstrap_draws_shared_across_contrasts_and_scoring_versions=True,
                    inference='Exploratory task-paired comparisons over the 12 benchmark tasks; not a model-only or general task-population claim.',
                    implementation_notes=['Python runtime is 3.12.14 versus planned 3.12.13; patch-version difference disclosed, frozen plan not rewritten.',
                    'NumPy 2.3.5 matches frozen plan. Matplotlib is an added rendering dependency.',
                    'Wilson intervals are descriptive run-level intervals; they do not adjust for within-task dependence.',
                    'Pairwise percentile intervals are unadjusted 95% task-bootstrap intervals; p values use Holm across six comparisons separately per scoring version.',
                    'Original-score tables are a baseline for later full sensitivity reporting; this stage covers success outcomes only.'])
    (ROOT/'results/core_success_manifest.json').write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8')
    print(json.dumps([r for r in summaries if r['scoring']=='reviewed' and r['level']=='overall'],indent=2))
    print(json.dumps([r for r in pairs if r['scoring']=='reviewed'],indent=2))


if __name__ == '__main__':
    main()
