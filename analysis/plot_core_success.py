"""Render thesis Figures 8–10: combined success, tiers and paired contrasts.

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
    DATA=ROOT/'results/tables/success_summaries.csv'
    rows=list(csv.DictReader(DATA.open(encoding='utf-8')))
    S=['cursor','devin','gpt-5.4','qwen2.5-coder-7b-instruct']
    L=['Cursor','Devin Desktop','GPT-5.4','Qwen2.5-Coder\n7B-Instruct']
    C=['#0072B2','#009E73','#CC79A7','#777777']
    def row(s,level='overall',group='all'):
        return next(r for r in rows if r['scoring']=='reviewed' and r['system']==s and r['level']==level and r['group']==group)
    R=[row(s) for s in S]
    assert [int(r['successes']) for r in R]==[35,33,34,0]
    assert all(int(r['n'])==36 for r in R)
    plt.rcParams.update({'font.family':'DejaVu Sans','font.size':9,'axes.labelsize':9,'axes.titlesize':11,'pdf.fonttype':42,'svg.fonttype':'none','axes.spines.top':False,'axes.spines.right':False})
    def save(fig,name):
        for ext in ['png','pdf','svg']: fig.savefig(OUT/f'{name}.{ext}',dpi=300,facecolor='white')
        plt.close(fig)
    def overall(ax,style='points'):
        for i,r in enumerate(R):
            x,lo,hi=[100*float(r[k]) for k in ['rate','ci_low','ci_high']]
            ax.axhspan(i-.43,i+.43,color='#f4f6f8' if i%2==0 else 'white',zorder=0)
            if style=='bars':
                ax.barh(i,x,height=.48,color='#87ceeb',zorder=2)
            ax.errorbar(x,i,xerr=[[x-lo],[hi-x]],fmt=['o','s','^','D'][i],color=C[i] if style=='points' else '#27408b',capsize=3,ms=5,lw=1.3,zorder=3)
            ax.text(113,i,f"{int(r['successes'])}/36",va='center',ha='center',fontsize=9)
            ax.text(136,i,str(36-int(r['successes'])),va='center',ha='center',fontsize=9)
            ax.text(166,i,f'{x:.1f}%',va='center',ha='right',fontsize=9,fontweight='bold')
        ax.set_yticks(range(4),L); ax.set_ylim(3.6,-.65); ax.set_xlim(-3,170)
        ax.set_xticks([0,25,50,75,100]); ax.set_xlabel('Successful runs (%)',loc='left')
        ax.tick_params(axis='y',length=0,pad=10); ax.spines['left'].set_visible(False)
        ax.spines['bottom'].set_bounds(0,100)
        ax.grid(axis='x',color='#e4e8eb',lw=.6);ax.set_axisbelow(True)
        ax.text(113,-.75,'Success',ha='center',fontsize=8,color='#53616c');ax.text(136,-.75,'Failure',ha='center',fontsize=8,color='#53616c');ax.text(166,-.75,'Rate',ha='right',fontsize=8,color='#53616c')

    fig=plt.figure(figsize=(7.1,6.3))
    fig.text(.04,.965,'Reviewed task success',fontsize=15,fontweight='bold')
    fig.text(.04,.931,'Four configured systems · 12 tasks · three repetitions per task',fontsize=9,color='#53616c')
    fig.text(.04,.885,'a',fontweight='bold',fontsize=12)
    ax=fig.add_axes([.27,.59,.70,.27]);overall(ax)
    fig.text(.04,.495,'b',fontweight='bold',fontsize=12)
    ax=fig.add_axes([.27,.11,.70,.36])
    tasks=sorted({r['group'] for r in rows if r['level']=='task'})
    values=np.array([[int(row(s,'task',t)['successes']) for t in tasks] for s in S])
    assert np.array_equal(values.sum(axis=1),[35,33,34,0])
    palette=['#f0f3f6','#bfd2e4','#759cc1','#27408b']
    ax.imshow(values,cmap=ListedColormap(palette),vmin=-.5,vmax=3.5,aspect='auto')
    ax.set_yticks(range(4),L);ax.set_xticks(range(12),[t[-2:] for t in tasks],fontsize=8)
    ax.tick_params(length=0,pad=9)
    for i in range(4):
        for j in range(12):ax.text(j,i,f'{values[i,j]}/3',ha='center',va='center',fontsize=8,color='white' if values[i,j]>=2 else '#273746')
    for j in np.arange(.5,12,1): ax.axvline(j,color='white',lw=1)
    for i in np.arange(.5,4,1):ax.axhline(i,color='white',lw=1)
    for j in [2.5,5.5,8.5]:ax.axvline(j,color='white',lw=5)
    for j in range(4):ax.text(j*3+1,-.85,f'L{j+1}',ha='center',fontweight='bold',fontsize=9)
    for spine in ax.spines.values():spine.set_visible(False)
    ax.set_xlabel('Task within architectural tier',labelpad=10)
    save(fig,'success_summary')

    print('Verified overall counts 35/33/34/0, failures 1/3/2/36; task sums match.')

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

    # 1: separate tiers rather than densely offset points sharing four rows.
    fig,axs=plt.subplots(2,2,figsize=(7.2,5.6));fig.subplots_adjust(left=.18,right=.96,top=.76,bottom=.17,wspace=.35,hspace=.55)
    title(fig,'Success across architectural tiers','Reviewed scoring · nine runs per system per tier · three distinct tasks per tier')
    for tier,ax in enumerate(axs.flat,1):
        stripe(ax,4)
        for i,s in enumerate(S):
            r=success(s,level='tier',group=str(tier));point(ax,r,i,C[i]);ax.text(112,i,f"{r['successes']}/9",va='center',fontsize=8)
        ax.set_xlim(-4,133);ax.set_xticks([0,50,100]);ax.spines['bottom'].set_bounds(0,100)
        ax.set_yticks(range(4),SHORT);ax.set_title(f'L{tier}',loc='left',fontweight='bold')
        if tier>2:ax.set_xlabel('Successful runs (%)')
    fig.text(.035,.045,'Bars: descriptive 95% Wilson intervals; within-task dependence is not adjusted.\nDevin = Devin Desktop; Qwen = Qwen2.5-Coder-7B-Instruct.',fontsize=7.5,color=GREY,linespacing=1.4)
    save(fig,'success_by_tier')

    # 2: preserve bootstrap intervals and expose the adjusted tests separately.
    pairs=[r for r in table('pairwise_success') if r['scoring']=='reviewed']
    fig,ax=plt.subplots(figsize=(7.2,4.9));fig.subplots_adjust(left=.30,right=.97,top=.76,bottom=.27)
    title(fig,'Paired system comparisons','Success-rate difference, A minus B · paired inference across 12 tasks')
    stripe(ax,6);label=dict(zip(S,SHORT))
    for i,r in enumerate(pairs):
        x,lo,hi=[100*float(r[k]) for k in ['risk_difference','ci_low','ci_high']]
        ax.errorbar(x,i,xerr=[[x-lo],[hi-x]],fmt='o',color=BLUE,ms=5,capsize=3,lw=1.3)
        ax.text(114,i,f'{x:+.1f}',va='center',ha='center',fontsize=8)
        ax.text(143,i,f"{float(r['p_holm']):.3f}" if float(r['p_holm'])==1 else f"{float(r['p_holm']):.5f}",va='center',ha='center',fontsize=8)
    ax.text(114,-.85,'Δ (pp)',ha='center',fontsize=8,color=GREY);ax.text(143,-.85,'Holm p',ha='center',fontsize=8,color=GREY)
    ax.set_yticks(range(6),[label[r['system_a']]+' − '+label[r['system_b']] for r in pairs]);ax.set_xlim(-20,160);ax.set_xticks([-20,0,25,50,75,100]);ax.spines['bottom'].set_bounds(-20,100)
    ax.axvline(0,color='#77838e',ls='--',lw=.8);ax.set_xlabel('Difference (percentage points)',loc='left')
    fig.text(.035,.06,'Bars: unadjusted 95% percentile intervals from 10,000 task-bootstrap resamples.\nHolm p: exact task-label-swap tests; six contrasts. Intervals are not simultaneous.\nDevin = Devin Desktop; Qwen = Qwen2.5-Coder-7B-Instruct.',fontsize=7.5,color=GREY,linespacing=1.4)
    save(fig,'success_pairwise')


    print('Rendered thesis Figures 8–10 from published tables.')


if __name__ == "__main__":
    main()
