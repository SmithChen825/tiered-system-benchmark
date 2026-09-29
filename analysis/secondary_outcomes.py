"""Planned descriptive outcomes and original/reviewed sensitivity; no new runs."""
import csv
import hashlib
import json
import platform
from pathlib import Path
import numpy as np
from core_success import SYSTEMS, write_csv

ROOT=Path(__file__).resolve().parents[1]


def quantiles(values):
    if not values:
        return dict(n=0,median=None,q1=None,q3=None)
    q1,median,q3=np.quantile(values,[.25,.5,.75],method='linear')
    return dict(n=len(values),median=float(median),q1=float(q1),q3=float(q3))


def ratio(numerator,denominator):
    return numerator/denominator if denominator else None


def main():
    source=ROOT/'data/main/analysis_dataset.csv'
    rows=list(csv.DictReader(source.open(encoding='utf-8',newline='')))
    assert len(rows)==len({r['run_id'] for r in rows})==144
    tables=ROOT/'results/tables'
    timing,diagnostics,task_diagnostics,robustness,clarification,transitions=[],[],[],[],[],[]
    for version in ('original','reviewed'):
        for system in SYSTEMS:
            selected=[r for r in rows if r['system_id']==system]
            assert len(selected)==36
            for population in ('all_valid','successful_valid'):
                subset=[r for r in selected if population=='all_valid' or int(r[version+'_success'])]
                timing.append(dict(scoring=version,system=system,population=population,**quantiles([float(r['elapsed_seconds']) for r in subset])))
            for measure in ('functional','architecture'):
                values=[float(r[f'{version}_{measure}_proportion']) for r in selected]
                diagnostics.append(dict(scoring=version,system=system,measure=measure,**quantiles(values)))
                for task in sorted({r['task_id'] for r in selected}):
                    values=[float(r[f'{version}_{measure}_proportion']) for r in selected if r['task_id']==task]
                    assert len(values)==3
                    task_diagnostics.append(dict(scoring=version,system=system,task=task,measure=measure,**quantiles(values)))
            eligible=[r for r in selected if int(r['robustness_eligible'])]
            assert len(eligible)==18
            numerator=sum(int(r[version+'_autonomous_success']) for r in eligible)
            assert numerator==sum(int(r[version+'_success']) and int(r['clarification_responses'])==0 for r in eligible)
            robustness.append(dict(scoring=version,system=system,eligible_n=18,autonomous_success_n=numerator,rate=numerator/18,response_runs=sum(int(r['clarification_responses'])>0 for r in eligible)))
    for system in SYSTEMS:
        selected=[r for r in rows if r['system_id']==system]
        opportunity=[r for r in selected if int(r['clarification_opportunity'])]
        complete=[r for r in selected if not int(r['clarification_opportunity'])]
        req,acc,resp=[sum(int(r['clarification_'+k]) for r in selected) for k in ('requests','authorized_requests','responses')]
        captured=sum(int(r['clarification_authorized_requests'])>0 for r in opportunity)
        unnecessary=sum(int(r['clarification_requests'])>0 for r in complete)
        assert len(opportunity)==3 and len(complete)==33
        clarification.append(dict(system=system,N_req=req,N_acc=acc,N_resp=resp,opportunity_n=3,captured_runs=captured,opportunity_capture=captured/3,request_precision=ratio(acc,req),complete_brief_n=33,unnecessary_request_runs=unnecessary,unnecessary_request_rate=unnecessary/33))
    for r in rows:
        record={k:r[k] for k in ('run_id','system_id','task_id','stop_reason')}
        for version in ('original','reviewed'):
            record[version+'_success']=int(r[version+'_success'])
            for measure in ('functional','architecture'):
                record[f'{version}_{measure}_passed']=int(r[f'{version}_{measure}_passed'])
                record[f'{version}_{measure}_applicable']=int(r[f'{version}_{measure}_applicable'])
        record['success_changed']=int(record['original_success']!=record['reviewed_success'])
        record['diagnostics_changed']=int(any(record['original_'+m+'_'+k]!=record['reviewed_'+m+'_'+k] for m in ('functional','architecture') for k in ('passed','applicable')))
        transitions.append(record)
    pairs=list(csv.DictReader((tables/'pairwise_success.csv').open(encoding='utf-8')))
    pair_sensitivity=[]
    for a,b in [(p['system_a'],p['system_b']) for p in pairs if p['scoring']=='reviewed']:
        old=next(p for p in pairs if p['scoring']=='original' and p['system_a']==a and p['system_b']==b)
        new=next(p for p in pairs if p['scoring']=='reviewed' and p['system_a']==a and p['system_b']==b)
        d=dict(system_a=a,system_b=b)
        for version,p in [('original',old),('reviewed',new)]:
            for k in ('risk_difference','ci_low','ci_high','p_exact','p_holm'):
                d[version+'_'+k]=float(p[k])
            d[version+'_reject_holm_005']=int(p['reject_holm_005'])
        pair_sensitivity.append(d)
    for name,values in [('elapsed_time',timing),('diagnostic_correctness',diagnostics),('task_diagnostics',task_diagnostics),('clarification',clarification),('robustness',robustness),('scoring_transitions',transitions),('pairwise_sensitivity',pair_sensitivity)]:
        write_csv(tables/(name+'.csv'),values)
    elapsed_unchanged=all({k:v for k,v in timing[i].items() if k!='scoring'}=={k:v for k,v in timing[i+8].items() if k!='scoring'} for i in range(0,8,2))
    assert elapsed_unchanged
    manifest=dict(source_commit='43c29bc4e01bdb2898c3c36e70bc1668872d1255',dataset_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),python=platform.python_version(),numpy=np.__version__,quantiles='NumPy linear',review_version='public-contract-audit/2026-09-26',scope='Descriptive secondary outcomes and scoring sensitivity, not failure-cause coding.',success_transitions=sum(r['success_changed'] for r in transitions),diagnostic_transitions=sum(r['diagnostics_changed'] for r in transitions),invariants={'all_valid_elapsed_unchanged':elapsed_unchanged,'clarification_inputs':'Single shared set of recorded request/response fields; no scoring-version transformation'},notes=['Same 144 run IDs and elapsed times under both scoring versions; successful-only populations may change.', 'Request precision is null if no requests; successful-only timing is null if no successes.', 'Diagnostic summaries weight runs equally; no pooled check denominator or weighted total score.', 'Robustness is successful without evaluator clarification response, not proof of recovery from every fault.'])
    (ROOT/'results/secondary_manifest.json').write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'timing':timing,'clarification':clarification,'robustness':robustness,'success_changes':manifest['success_transitions'],'diagnostic_changes':manifest['diagnostic_transitions']},indent=2))


if __name__=='__main__':
    main()
