"""Main-text timing, diagnostics, robustness and scoring-sensitivity figures."""
import argparse
import csv
import importlib.util
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
from plot_core_success import ROOT,SYSTEMS,LABELS,COLORS
plt.rcParams.update({'font.family':'sans-serif','font.sans-serif':['DejaVu Sans'],'svg.fonttype':'none','pdf.fonttype':42})


def read(name):
    return list(csv.DictReader((ROOT/name).open(encoding='utf-8',newline='')))


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--alignment-helper',type=Path)
    args=parser.parse_args()
    require_matplotlib_panel_alignment=None
    if args.alignment_helper:
        spec=importlib.util.spec_from_file_location('alignment',args.alignment_helper)
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        require_matplotlib_panel_alignment=module.require_matplotlib_panel_alignment
    out=ROOT/'results/figures'
    def save(fig,name,exclude=None):
        fig.canvas.draw()
        if require_matplotlib_panel_alignment:
            require_matplotlib_panel_alignment(fig,json_out=str(out/(name+'.alignment.json')),exclude_axes=exclude or [],strict=True)
        fig.savefig(out/f'{name}.svg')
        fig.savefig(out/f'{name}.pdf',metadata={'Creator':'TSB secondary outcomes'})
        fig.savefig(out/f'{name}.png',dpi=600)
        plt.close(fig)
    def letter(ax,s):
        ax.annotate(s,xy=(0,1),xycoords='axes fraction',xytext=(-25,18),textcoords='offset points',fontweight='bold',fontsize=11)
    short=['Cursor','Devin','GPT-5.4','Qwen']
    rows=read('data/main/analysis_dataset.csv')
    fig,axes=plt.subplots(1,2,figsize=(7.08,4.5),sharey=True)
    fig.subplots_adjust(left=.10,right=.97,bottom=.20,top=.80,wspace=.22)
    for a,(ax,pop) in enumerate(zip(axes,['all_valid','successful_valid'])):
        labels=[]
        for i,s in enumerate(SYSTEMS):
            selected=[r for r in rows if r['system_id']==s and (pop=='all_valid' or int(r['reviewed_success']))]
            labels.append(f'{short[i]}\n(n={len(selected)})'+ ('\nNo successes' if not selected else ''))
            values=[float(r['elapsed_seconds']) for r in selected]
            assert all(v>0 for v in values)
            if values:
                ax.boxplot([values],positions=[i],widths=.52,whis=1.5,showfliers=False,patch_artist=True,boxprops={'facecolor':'#EEEEEE'},medianprops={'color':'black'},manage_ticks=False)
                offsets=np.linspace(-.16,.16,len(selected))
                for offset,r,value in zip(offsets,selected,values):
                    success=int(r['reviewed_success'])
                    ax.scatter(i+offset,value,s=13,marker='o' if success else 'x',color='#0072B2' if success else '#D55E00',alpha=.75,zorder=3)
        ax.set_xticks(range(4),labels,fontsize=8);ax.set_xlim(-.5,3.5);ax.set_yscale('log');ax.set_ylim(5,1500)
        ax.set_title('a  All valid runs' if a==0 else 'b  Successful runs',pad=12)
        ax.grid(axis='y',alpha=.15);ax.set_axisbelow(True)
    axes[0].set_ylabel('Elapsed seconds (log scale)')
    fig.text(.5,.94,'Task duration and outcome',ha='center',fontsize=11)
    fig.text(.5,.875,'Blue circles: success   |   Orange crosses: unsuccessful',ha='center',fontsize=8)
    save(fig,'elapsed_time')

    diag=[r for r in read('results/tables/task_diagnostics.csv') if r['scoring']=='reviewed']
    tasks=sorted({r['task'] for r in diag})
    fig,axes=plt.subplots(1,2,figsize=(7.08,5.4),sharey=True)
    fig.subplots_adjust(left=.12,right=.88,bottom=.15,top=.85,wspace=.20)
    for j,(ax,measure) in enumerate(zip(axes,['functional','architecture'])):
        values=np.array([[float(next(r for r in diag if r['task']==t and r['system']==s and r['measure']==measure)['median']) for s in SYSTEMS] for t in tasks])
        im=ax.imshow(values,vmin=0,vmax=1,cmap='Blues',aspect='auto',interpolation='nearest')
        ax.set_xticks(range(4),['Cursor','Devin','GPT-5.4','Qwen'],fontsize=8)
        ax.set_yticks(range(12),tasks,fontsize=8);ax.set_title(measure.capitalize(),pad=12);letter(ax,'ab'[j])
        for y in range(12):
            for x in range(4):
                ax.text(x,y,f'{100*values[y,x]:.0f}',ha='center',va='center',fontsize=7,color='white' if values[y,x]>=.65 else '#222222')
    cax=fig.add_axes([.91,.15,.02,.70]);bar=fig.colorbar(im,cax=cax,ticks=[0,.5,1]);bar.ax.set_yticklabels(['0','50','100']);bar.set_label('Median checks passed (%)',fontsize=8)
    fig.text(.5,.965,'Functional and architectural diagnostics',ha='center',fontsize=11)
    save(fig,'diagnostic_checks',exclude=[cax])

    robust=[r for r in read('results/tables/robustness.csv') if r['scoring']=='reviewed']
    fig,ax=plt.subplots(figsize=(7.08,3.2));fig.subplots_adjust(left=.35,right=.96,bottom=.22,top=.80)
    for i,s in enumerate(SYSTEMS):
        r=next(r for r in robust if r['system']==s)
        ax.scatter(float(r['rate'])*100,i,s=36,color=COLORS[i])
    ax.set_yticks(range(4),[f'{label} ({next(r for r in robust if r["system"]==s)["autonomous_success_n"]}/18)' for label,s in zip(LABELS,SYSTEMS)])
    ax.invert_yaxis();ax.set_xlim(-3,103);ax.set_xticks([0,25,50,75,100]);ax.grid(axis='x',alpha=.15);ax.set_axisbelow(True)
    ax.set_xlabel('Successful without evaluator clarification response (%)');ax.set_title('L3/L4 success without clarification responses',pad=18)
    save(fig,'robustness')

    summary=[r for r in read('results/tables/success_summaries.csv') if r['level']=='overall']
    sensitivity_labels=[*LABELS[:3],'Qwen']
    fig,ax=plt.subplots(figsize=(7.08,3.4));fig.subplots_adjust(left=.35,right=.96,bottom=.21,top=.78)
    for i,s in enumerate(SYSTEMS):
        old=next(r for r in summary if r['system']==s and r['scoring']=='original');new=next(r for r in summary if r['system']==s and r['scoring']=='reviewed')
        xs=[100*float(old['rate']),100*float(new['rate'])]
        ax.plot(xs,[i,i],color='#888888',lw=1.5)
        ax.scatter(xs[0],i,s=44,marker='s',facecolors='white',edgecolors='#555555',zorder=3)
        ax.scatter(xs[1],i,s=24,color='#0072B2',zorder=4)
    ax.set_yticks(range(4),[f'{label} ({next(r for r in summary if r["system"]==s and r["scoring"]=="original")["successes"]} → {next(r for r in summary if r["system"]==s and r["scoring"]=="reviewed")["successes"]}/36)' for label,s in zip(sensitivity_labels,SYSTEMS)])
    ax.invert_yaxis();ax.set_xlim(-3,103);ax.set_xticks([0,25,50,75,100]);ax.set_xlabel('Successful runs (%)');ax.grid(axis='x',alpha=.15);ax.set_axisbelow(True)
    fig.text(.66,.95,'Sensitivity to scoring review',ha='center',fontsize=11)
    fig.text(.66,.865,'Open square: original   |   Blue circle: reviewed',ha='center',fontsize=8)
    save(fig,'scoring_sensitivity')


if __name__=='__main__':
    main()
