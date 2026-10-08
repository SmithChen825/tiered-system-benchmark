"""Render thesis Figures 11–16: timing, diagnostics, no-response success, failures and sensitivity.

Read published repository data; write PDF, SVG and 300 dpi PNG to results/figures.
No model calls or changes to scores and statistical procedures.
"""
from pathlib import Path
import csv
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.colors import ListedColormap, LinearSegmentedColormap


def main():
    ROOT=Path(__file__).resolve().parents[1]
    OUT=ROOT/'results/figures'
    OUT.mkdir(parents=True, exist_ok=True)
    SRC=ROOT
    S=['cursor','devin','gpt-5.4','qwen2.5-coder-7b-instruct']
    L=['Cursor','Devin Desktop','GPT-5.4','Qwen2.5-Coder\n7B-Instruct']
    SHORT=['Cursor','Devin','GPT-5.4','Qwen']
    C=['#0072B2','#009E73','#CC79A7','#777777']
    BLUE='#27408b'; GREY='#53616c'
    CM=LinearSegmentedColormap.from_list('thesis',['#f0f3f6','#bfd2e4','#759cc1',BLUE])
    plt.rcParams.update({'font.family':'DejaVu Sans','font.size':9,'axes.labelsize':9,'axes.titlesize':10,'xtick.labelsize':8,'ytick.labelsize':9,'pdf.fonttype':42,'svg.fonttype':'none','axes.spines.top':False,'axes.spines.right':False,'axes.linewidth':.7})
    def read(name):return list(csv.DictReader((SRC/name).open(encoding='utf-8')))
    def table(name):return read('results/tables/'+name+'.csv')
    summary=table('success_summaries')
    def success(s,scoring='reviewed',level='overall',group='all'):
        return next(r for r in summary if r['system']==s and r['scoring']==scoring and r['level']==level and r['group']==group)
    names=[]
    def save(fig,name):
        fig.canvas.draw()
        for ext in ['png','pdf','svg']:fig.savefig(OUT/f'{name}.{ext}',dpi=300,facecolor='white')
        names.append(name);plt.close(fig)
    def title(fig,t,sub):
        fig.text(.035,.955,t,fontsize=14,fontweight='bold',va='top')
        fig.text(.035,.895,sub,fontsize=8.5,color=GREY,va='top')
    def stripe(ax,n):
        for i in range(n):
            if i%2==0:ax.axhspan(i-.45,i+.45,color='#f4f6f8',zorder=0)
        ax.set_ylim(n-.6,-.6);ax.tick_params(axis='y',length=0,pad=8);ax.spines['left'].set_visible(False)
        ax.grid(axis='x',color='#e4e8eb',lw=.6);ax.set_axisbelow(True)
    def point(ax,r,y,color):
        x,lo,hi=[100*float(r[k]) for k in ['rate','ci_low','ci_high']]
        ax.errorbar(x,y,xerr=[[x-lo],[hi-x]],fmt='o',color=color,capsize=3,ms=5,lw=1.2,zorder=3)

    # 3: real observations and boxes on the same log axis; no KDE smoothing.
    runs=read('data/main/analysis_dataset.csv');assert len(runs)==144
    fig,axs=plt.subplots(2,1,figsize=(7.2,6.1));fig.subplots_adjust(left=.27,right=.91,top=.77,bottom=.19,hspace=.50)
    title(fig,'Elapsed time by outcome population','Every observation shown · blue circles: success · orange crosses: unsuccessful')
    medians={}
    for panel,(ax,only) in enumerate(zip(axs,[False,True])):
        stripe(ax,4);labs=[]
        for i,s in enumerate(S):
            rr=[r for r in runs if r['system_id']==s and (not only or int(r['reviewed_success']))]
            vals=[float(r['elapsed_seconds']) for r in rr];labs.append(f'{SHORT[i]}  (n={len(vals)})')
            if vals:
                ax.boxplot([vals],positions=[i],orientation='horizontal',widths=.45,whis=1.5,showfliers=False,manage_ticks=False,patch_artist=True,boxprops={'facecolor':'#d8e8f2','edgecolor':'#8299ad'},medianprops={'color':BLUE,'linewidth':1.4})
                for off,r,v in zip(np.linspace(-.16,.16,len(rr)),rr,vals):ax.scatter(v,i+off,marker='o' if int(r['reviewed_success']) else 'x',s=12,color='#0072B2' if int(r['reviewed_success']) else '#D55E00',alpha=.75,zorder=3)
                medians[f'{only}-{s}']=float(np.median(vals))
            else:ax.text(45,i,'No successful observations',va='center',fontsize=8,color=GREY)
        ax.set_xscale('log');ax.set_xlim(5,1500);ax.set_xticks([10,30,100,300,1000],['10','30','100','300','1,000']);ax.set_yticks(range(4),labs)
        ax.set_title('a  All valid runs' if panel==0 else 'b  Reviewed successful runs',loc='left',fontweight='bold',pad=12)
    axs[1].set_xlabel('Elapsed seconds (log scale)')
    fig.text(.035,.025,'Boxes: Q1–Q3; centre line: median; whiskers: 1.5 IQR, computed in seconds.\nUnsuccessful durations are times to termination, not successful repair times.\nDevin = Devin Desktop; Qwen = Qwen2.5-Coder-7B-Instruct.',fontsize=7.2,color=GREY,linespacing=1.4)
    save(fig,'elapsed_time')

    # 4: rows become systems, aligned with installed Figure 8.
    diag=[r for r in table('task_diagnostics') if r['scoring']=='reviewed'];tasks=sorted({r['task'] for r in diag})
    fig,axs=plt.subplots(2,1,figsize=(7.2,6.5));fig.subplots_adjust(left=.25,right=.94,top=.77,bottom=.27,hspace=.65)
    title(fig,'Functional and architectural diagnostics','Median proportion of applicable checks passed · three repetitions per cell')
    for j,(ax,measure) in enumerate(zip(axs,['functional','architecture'])):
        vals=np.array([[float(next(r for r in diag if r['task']==t and r['system']==s and r['measure']==measure)['median'])*100 for t in tasks] for s in S])
        im=ax.imshow(vals,vmin=0,vmax=100,cmap=CM,aspect='auto');ax.set_yticks(range(4),SHORT);ax.set_xticks(range(12),[t[-2:] for t in tasks]);ax.tick_params(length=0,pad=6)
        for y in range(4):
            for x in range(12):ax.text(x,y,f'{vals[y,x]:.0f}',ha='center',va='center',fontsize=7,color='white' if vals[y,x]>=65 else '#273746')
        for x in np.arange(.5,12,1):ax.axvline(x,color='white',lw=.8)
        for y in np.arange(.5,4,1):ax.axhline(y,color='white',lw=.8)
        for x in [2.5,5.5,8.5]:ax.axvline(x,color='white',lw=4)
        for tier in range(4):ax.text(3*tier+1,-.80,f'L{tier+1}',ha='center',fontsize=8,fontweight='bold')
        ax.set_title(('a  Functional' if j==0 else 'b  Architectural'),loc='left',pad=27,fontweight='bold')
        for sp in ax.spines.values():sp.set_visible(False)
    cax=fig.add_axes([.40,.18,.40,.018]);fig.colorbar(im,cax=cax,orientation='horizontal',ticks=[0,25,50,75,100],label='Median checks passed (%)')
    fig.text(.035,.03,'Whole-number labels; colour uses unrounded medians. No pooling of check denominators.\nCeiling medians can conceal failed repetitions. Read alongside binary success.\nDevin = Devin Desktop; Qwen = Qwen2.5-Coder-7B-Instruct.',fontsize=7.2,color=GREY,linespacing=1.35)
    save(fig,'diagnostic_checks')

    # 5: descriptive rate; do not add unrequested inference.
    rob=[r for r in table('robustness') if r['scoring']=='reviewed']
    fig,ax=plt.subplots(figsize=(7.2,3.8));fig.subplots_adjust(left=.27,right=.96,top=.72,bottom=.29)
    title(fig,'L3/L4 success without clarification responses','Six tasks · three repetitions each · 18 eligible observations per system')
    stripe(ax,4)
    for i,s in enumerate(S):
        r=next(r for r in rob if r['system']==s);x=100*float(r['rate']);ax.scatter(x,i,color=C[i],s=30,zorder=3)
        ax.text(108,i,f"{r['autonomous_success_n']}/18",va='center',fontsize=9);ax.text(145,i,f'{x:.1f}%',ha='right',va='center',fontweight='bold')
    ax.set_yticks(range(4),L);ax.set_xlim(-3,149);ax.set_xticks([0,25,50,75,100]);ax.spines['bottom'].set_bounds(0,100);ax.set_xlabel('Successful runs (%)',loc='left')
    fig.text(.035,.05,'All eligible runs received zero evaluator clarification responses. These values therefore equal\nL3/L4 success rates here; they are not an independent measure of recovery. No intervals shown.',fontsize=7.5,color=GREY,linespacing=1.4)
    save(fig,'robustness')

    # 6: paired scoring versions, direct original/reviewed counts.
    fig,ax=plt.subplots(figsize=(7.2,4.0));fig.subplots_adjust(left=.27,right=.96,top=.71,bottom=.26)
    title(fig,'Sensitivity to scoring review','Same 36 observations per system · open square: original · filled circle: reviewed')
    stripe(ax,4)
    for i,s in enumerate(S):
        a,b=success(s,'original'),success(s);x0,x1=100*float(a['rate']),100*float(b['rate'])
        ax.plot([x0,x1],[i,i],color='#9aabb7',lw=2);ax.scatter(x0,i,marker='s',s=62,facecolors='white',edgecolors=BLUE,zorder=3);ax.scatter(x1,i,s=20,color=BLUE,zorder=4)
        ax.text(111,i,f"{a['successes']} → {b['successes']}",ha='center',va='center',fontsize=9);ax.text(142,i,f'{x1-x0:+.1f}',ha='center',va='center',fontsize=9)
    ax.text(111,-.9,'Successes / 36',ha='center',fontsize=8,color=GREY);ax.text(142,-.9,'Δ (pp)',ha='center',fontsize=8,color=GREY)
    ax.set_yticks(range(4),L);ax.set_xlim(-3,155);ax.set_xticks([0,25,50,75,100]);ax.spines['bottom'].set_bounds(0,100);ax.set_xlabel('Successful runs (%)',loc='left')
    fig.text(.035,.05,'Connections compare scoring versions, not new runs or learning over time.\nOverlapping marks indicate no change; original and reviewed intervals remain in the analysis tables.',fontsize=7.5,color=GREY,linespacing=1.4)
    save(fig,'scoring_sensitivity')

    # 7,8: validate stage/category aggregations against existing tables.
    failure=table('failure_coding');assert len(failure)==42
    stages=['No accepted action','Inspection attempts; no edit','Edited and submitted; checks fail']
    N=np.array([sum(r['system']==s for r in failure) for s in S]);assert list(N)==[1,3,2,36]
    counts=np.array([[sum(r['system']==s and r['stage']==st for r in failure) for s in S] for st in stages]);assert np.array_equal(counts.sum(axis=0),N)
    for r in table('failure_stage_counts'):assert counts[stages.index(r['stage']),S.index(r['system'])]==int(r['count'])
    fig,ax=plt.subplots(figsize=(7.2,5.0));fig.subplots_adjust(left=.29,right=.96,top=.64,bottom=.23)
    title(fig,'Observed stages of unsuccessful runs','All 42 unsuccessful runs retained · mutually exclusive descriptive stages')
    left=np.zeros(4)
    for ks,col,lab in zip(counts,['#7d8cba','#87ceeb','#f2a59d'],['No accepted action','Inspection/clarification; no edit','Edited submission; checks fail']):
        w=100*ks/N;ax.barh(range(4),w,left=left,height=.61,color=col,label=lab)
        for i,k in enumerate(ks):
            if k:ax.text(left[i]+w[i]/2,i,f'{k}/{N[i]} ({w[i]:.0f}%)',ha='center',va='center',fontsize=8,color='#192b3b')
        left+=w
    ax.set_yticks(range(4),[f'{lab}\n{n} unsuccessful / 36' for lab,n in zip(['Cursor','Devin Desktop','GPT-5.4','Qwen'],N)],fontsize=8);ax.set_ylim(3.65,-.65);ax.set_xlim(0,100);ax.set_xticks([0,25,50,75,100]);ax.tick_params(axis='y',length=0,pad=9);ax.spines['left'].set_visible(False);ax.set_xlabel("Share of each system's unsuccessful runs (%)")
    fig.legend(*ax.get_legend_handles_labels(),loc='upper left',bbox_to_anchor=(.29,.84),frameon=False,fontsize=8)
    fig.text(.035,.04,'The denominator differs by system. These categories describe observed progress,\nnot an ordinal capability score or a causal explanation of failure.\nQwen = Qwen2.5-Coder-7B-Instruct.',fontsize=7.5,color=GREY,linespacing=1.4)
    save(fig,'failure_stages')

    cats=['premature_submission','repeated_ineffective_commands','incorrect_api_or_database_assumption','missed_cascading_dependency','unnecessary_clarification','failed_final_state_validation','other_evidence_supported']
    catlabels=['Premature submission','Repeated ineffective\ncommands','Incorrect API/database\ncontract','Missed cascading\ndependency','Unnecessary clarification','Failed final-state validation','Other supported behaviour']
    v=np.array([[sum(r['system']==s and c in r['categories'].split(';') for r in failure) for s in S] for c in cats])
    for r in table('failure_category_counts'):assert v[cats.index(r['category']),S.index(r['system'])]==int(r['count'])
    fig,ax=plt.subplots(figsize=(7.2,5.7));fig.subplots_adjust(left=.35,right=.88,top=.77,bottom=.26)
    title(fig,'Evidence-supported failure categories','Documented run counts · shared 0–36 colour scale · categories may overlap')
    im=ax.imshow(v,cmap=CM,vmin=0,vmax=36,aspect='auto');ax.set_yticks(range(7),catlabels,fontsize=8);ax.set_xticks(range(4),['Cursor*\nn = 1','Devin*\nn = 3','GPT-5.4\nn = 2','Qwen\nn = 36']);ax.tick_params(length=0,pad=9)
    for y in range(7):
        for x in range(4):ax.text(x,y,str(v[y,x]),va='center',ha='center',fontsize=11,fontweight='bold' if v[y,x] else 'normal',color='white' if v[y,x]>23 else '#273746')
    for y in np.arange(.5,7,1):ax.axhline(y,color='white',lw=2)
    for x in np.arange(.5,4,1):ax.axvline(x,color='white',lw=2)
    for sp in ax.spines.values():sp.set_visible(False)
    cax=fig.add_axes([.92,.26,.015,.51]);fig.colorbar(im,cax=cax,ticks=[0,12,24,36],label='Run count')
    fig.text(.035,.055,'* Native interaction trajectories unavailable; final-state evidence only.\nZero means no assigned code, not established absence of behaviour.\nDevin = Devin Desktop; Qwen = Qwen2.5-Coder-7B-Instruct. n = unsuccessful runs.',fontsize=7.5,color=GREY,linespacing=1.4)
    save(fig,'failure_categories')


    print('Rendered thesis Figures 11–16; verified 144 runs and all 42 failure codes.')


if __name__ == "__main__":
    main()
