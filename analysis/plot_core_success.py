"""Four main-text figures from the reviewed success tables; no data exclusions."""
import argparse
import csv
import importlib.util
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
SYSTEMS = ['cursor','devin','gpt-5.4','qwen2.5-coder-7b-instruct']
LABELS = ['Cursor','Devin Desktop','GPT-5.4','Qwen2.5-Coder-7B-Instruct']
COLORS = ['#0072B2','#009E73','#CC79A7','#777777']
plt.rcParams.update({'font.family':'sans-serif','font.sans-serif':['DejaVu Sans'],'font.size':9,'axes.labelsize':9,
                    'axes.titlesize':11,'xtick.labelsize':8,'ytick.labelsize':9,
                    'pdf.fonttype':42,'svg.fonttype':'none','axes.spines.top':False,
                    'axes.spines.right':False,'axes.linewidth':.7,'savefig.dpi':300})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--alignment-helper', type=Path, help='Optional local geometry-audit helper; not needed to reproduce figures')
    args = parser.parse_args()
    audit = None
    if args.alignment_helper:
        spec = importlib.util.spec_from_file_location('alignment_audit',args.alignment_helper)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        audit = module.require_matplotlib_panel_alignment
    output = ROOT/'results/figures'
    output.mkdir(parents=True,exist_ok=True)
    def save(fig,name,exclude=None):
        fig.canvas.draw()
        if audit:
            audit(fig,json_out=str(output/(name+'.alignment.json')),exclude_axes=exclude or [],strict=True)
        fig.savefig(output/f'{name}.svg')
        fig.savefig(output/f'{name}.pdf',metadata={'Creator':'TSB core success analysis'})
        fig.savefig(output/f'{name}.png',dpi=600)
        plt.close(fig)
    with (ROOT/'results/tables/success_summaries.csv').open(encoding='utf-8') as f:
        summary = [r for r in csv.DictReader(f) if r['scoring']=='reviewed']
    def point(ax,r,y,color):
        x,lo,hi = [100*float(r[k]) for k in ('rate','ci_low','ci_high')]
        ax.errorbar(x,y,xerr=[[max(0,x-lo)],[max(0,hi-x)]],fmt='o',color=color,capsize=3,markersize=5,lw=1.2)
    fig,ax = plt.subplots(figsize=(7.08,3.15))
    fig.subplots_adjust(left=.34,right=.96,bottom=.22,top=.82)
    for i,s in enumerate(SYSTEMS):
        r=next(r for r in summary if r['level']=='overall' and r['system']==s)
        point(ax,r,i,COLORS[i])
    ax.set_yticks(range(4),[f'{label} ({next(r for r in summary if r["level"]=="overall" and r["system"]==s)["successes"]}/36)' for label,s in zip(LABELS,SYSTEMS)])
    ax.invert_yaxis(); ax.set_xlim(-3,103); ax.set_xticks(range(0,101,25))
    ax.set_xlabel('Successful runs (%)'); ax.set_title('Overall task success',pad=18)
    ax.grid(axis='x',alpha=.18); ax.set_axisbelow(True)
    save(fig,'success_overall')

    fig,ax=plt.subplots(figsize=(7.08,4.7))
    fig.subplots_adjust(left=.12,right=.96,bottom=.16,top=.78)
    for i,s in enumerate(SYSTEMS):
        for tier in range(1,5):
            r=next(r for r in summary if r['level']=='tier' and r['group']==str(tier) and r['system']==s)
            point(ax,r,(tier-1)*1.5+(i-1.5)*.23,COLORS[i])
        ax.plot([],[],color=COLORS[i],marker='o',ls='none',label=LABELS[i])
    ax.set_yticks(np.arange(4)*1.5,['L1','L2','L3','L4']); ax.invert_yaxis()
    ax.set_xlim(-3,103); ax.set_xticks(range(0,101,25)); ax.set_xlabel('Successful runs (%)')
    fig.suptitle('Success across architectural tiers',y=.98,fontsize=11)
    fig.legend(loc='upper center',bbox_to_anchor=(.53,.93),ncol=2,frameon=False,fontsize=8)
    ax.grid(axis='x',alpha=.18); ax.set_axisbelow(True)
    save(fig,'success_by_tier')

    tasks=sorted({r['group'] for r in summary if r['level']=='task'})
    counts=np.array([[int(next(r for r in summary if r['level']=='task' and r['group']==t and r['system']==s)['successes']) for s in SYSTEMS] for t in tasks])
    fig,ax=plt.subplots(figsize=(7.08,5.3))
    fig.subplots_adjust(left=.15,right=.85,bottom=.18,top=.90)
    im=ax.imshow(counts,vmin=0,vmax=3,cmap='Blues',aspect='auto',interpolation='nearest')
    ax.set_xticks(range(4),['Cursor','Devin Desktop','GPT-5.4','Qwen2.5-Coder\n7B-Instruct']); ax.set_yticks(range(12),tasks)
    ax.set_title('Task-level success',pad=16)
    for j in range(12):
        for i in range(4):
            ax.text(i,j,f'{counts[j,i]}/3',ha='center',va='center',color='white' if counts[j,i]>=2 else '#222222',fontsize=9)
    bar=fig.colorbar(im,ax=ax,fraction=.045,pad=.05,ticks=[0,1,2,3])
    bar.set_label('Successful repetitions',fontsize=8)
    save(fig,'success_by_task',exclude=[bar.ax])

    with (ROOT/'results/tables/pairwise_success.csv').open(encoding='utf-8') as f:
        pairs=[r for r in csv.DictReader(f) if r['scoring']=='reviewed']
    fig,ax=plt.subplots(figsize=(7.08,3.9))
    fig.subplots_adjust(left=.37,right=.96,bottom=.19,top=.85)
    short=dict(zip(SYSTEMS,['Cursor','Devin Desktop','GPT-5.4','Qwen']))
    for i,r in enumerate(pairs):
        x,lo,hi=[100*float(r[k]) for k in ('risk_difference','ci_low','ci_high')]
        ax.errorbar(x,i,xerr=[[max(0,x-lo)],[max(0,hi-x)]],fmt='o',color='#0072B2',capsize=3,lw=1.2,markersize=5)
    ax.set_yticks(range(6),[short[r['system_a']]+' − '+short[r['system_b']] for r in pairs]);ax.invert_yaxis()
    ax.axvline(0,color='#888888',lw=.8,ls='--');ax.set_xlim(-20,103);ax.set_xticks([-20,0,20,40,60,80,100])
    ax.set_xlabel('Success-rate difference (percentage points)')
    ax.set_title('Paired differences across 12 tasks',pad=18)
    ax.grid(axis='x',alpha=.15);ax.set_axisbelow(True)
    save(fig,'success_pairwise')


if __name__=='__main__':
    main()
