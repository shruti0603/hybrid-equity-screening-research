"""Monthly cross-sectional evaluation: IC, quantile portfolios w/ costs, benchmarks, ablations, walk-forward weights, bootstrap."""
import numpy as np, pandas as pd, itertools
from scipy import stats

def newey_west_t(x, lags=3):
    x=np.asarray(x,float); x=x[~np.isnan(x)]; n=len(x)
    if n<8: return np.nan
    m=x.mean(); u=x-m; v=u@u/n
    for l in range(1,lags+1): v+=2*(1-l/(lags+1))*(u[l:]@u[:-l])/n
    return float(m/np.sqrt(v/n)) if np.isfinite(v) and v > 0 else np.nan

def monthly_ic(scores, fwd):
    """scores, fwd: DataFrames (date x ticker). Spearman IC each month."""
    ic={}
    for d in scores.index:
        a=pd.concat([scores.loc[d],fwd.loc[d]],axis=1).dropna()
        if len(a)>=10: ic[d]=stats.spearmanr(a.iloc[:,0],a.iloc[:,1])[0]
    return pd.Series(ic)

def top_n_returns(scores, fwd, q=0.2, cost_bps=10.0):
    """Long equal-weight top fraction q; cost on one-way traded notional. Returns (gross, net, turnover)."""
    prev=pd.Series(dtype=float); g=[];nn=[];to=[];idx=[]
    for d in scores.index:
        s=scores.loc[d].dropna(); f=fwd.loc[d]
        s=s[s.index.isin(f.dropna().index)]
        if len(s)<10: continue
        k=max(int(round(len(s)*q)),1); sel=s.nlargest(k).index
        w=pd.Series(1.0/k,index=sel)
        # One-way traded notional: half L1 for fully invested rebalance;
        # initial purchase costs one full notional. Does not model intra-month weight drift.
        t=float(w.sub(prev,fill_value=0).abs().sum()/2) if len(prev) else 1.0
        gr=float((w*f[sel]).sum()); g.append(gr); nn.append(gr-t*cost_bps/1e4); to.append(t); idx.append(d); prev=w
    return pd.Series(g,idx),pd.Series(nn,idx),pd.Series(to,idx)

def ew_universe(fwd, scores_mask):
    """Constant-rule equal-weight benchmark over ALL names with valid return AND a valid score that month (same eligible set)."""
    ok=scores_mask.notna()&fwd.notna()
    return (fwd.where(ok)).mean(axis=1)

def perf(r, rf=0.0):
    r=r.replace([np.inf,-np.inf],np.nan).dropna()
    if r.empty:
        return dict(CAGR=np.nan,Sharpe=np.nan,MaxDD=np.nan,N=0)
    growth=(1+r).prod()
    a=float(growth**(12/len(r))-1) if growth>0 else np.nan
    ex=r-rf/12
    sd=ex.std(ddof=1)
    sh=float(ex.mean()/sd*np.sqrt(12)) if np.isfinite(sd) and sd>0 else np.nan
    cum=(1+r).cumprod(); dd=float((cum/cum.cummax()-1).min())
    return dict(CAGR=a,Sharpe=sh,MaxDD=dd,N=len(r))

def block_boot_diff(r1, r0, B=5000, block=6, seed=0):
    """Circular block bootstrap for annualized Sharpe difference (r1-r0 strategies, aligned)."""
    a=pd.concat([r1,r0],axis=1).replace([np.inf,-np.inf],np.nan).dropna().values
    n=len(a)
    if n<2:
        return dict(diff=np.nan,lo=np.nan,hi=np.nan,p_le0=np.nan)
    rng=np.random.default_rng(seed); out=[]
    for _ in range(B):
        starts=rng.integers(0,n,int(np.ceil(n/block))); ix=np.concatenate([(s+np.arange(block))%n for s in starts])[:n]
        x=a[ix]
        def sh(v):
            sd=v.std(ddof=1)
            return float(v.mean()/sd*np.sqrt(12)) if np.isfinite(sd) and sd>0 else np.nan
        out.append(sh(x[:,0])-sh(x[:,1]))
    out=np.asarray(out,float); out=out[np.isfinite(out)]
    if len(out)==0:
        return dict(diff=np.nan,lo=np.nan,hi=np.nan,p_le0=np.nan)
    return dict(diff=float(np.mean(out)),lo=float(np.percentile(out,2.5)),hi=float(np.percentile(out,97.5)),p_le0=float((out<=0).mean()))

def combos(comp, weights_list):
    """comp: dict name->DataFrame(date x ticker, 0..100). weights_list: dict label->dict(name->w). Weights renormalised over available comps."""
    res={}
    for lab,w in weights_list.items():
        num=sum(comp[k]*v for k,v in w.items()); den=sum(comp[k].notna()*v for k,v in w.items())
        res[lab]=num/den.replace(0,np.nan)
    return res

def walk_forward_weights(comp_names, comp, fwd, grid_step=0.1, min_hist=24):
    """Choose weights each month using ONLY past IC (expanding window), on a simplex grid. Returns score DataFrame."""
    k=len(comp_names); grid=[w for w in itertools.product(np.arange(0,1+1e-9,grid_step),repeat=k) if abs(sum(w)-1)<1e-9]
    dates=list(fwd.index); out=pd.DataFrame(index=fwd.index,columns=fwd.columns,dtype=float); chosen={}
    ics={w:[] for w in grid}
    for i,d in enumerate(dates):
        if i>=min_hist:
            best=max(grid,key=lambda w:np.nanmean(ics[w][-10**6:]) if len(ics[w]) else -9)
            chosen[d]=best
            num=sum(comp[c].loc[d]*wi for c,wi in zip(comp_names,best)); den=sum(comp[c].loc[d].notna()*wi for c,wi in zip(comp_names,best))
            out.loc[d]=num/den.replace(0,np.nan)
        # after d's *realised* fwd return becomes known (available at d+1), record IC for each weight set -- appended with a one-period lag
        if i>=1:
            dp=dates[i-1]
            for w in grid:
                s=sum(comp[c].loc[dp]*wi for c,wi in zip(comp_names,w)); a=pd.concat([s,fwd.loc[dp]],axis=1).dropna()
                if len(a)>=10: ics[w].append(stats.spearmanr(a.iloc[:,0],a.iloc[:,1])[0])
    return out,pd.Series(chosen)

def fama_macbeth(y, X, lags=3):
    """y: DataFrame date x ticker; X: dict name->DataFrame. Cross-sectional OLS each month; NW t-stats on time series of slopes."""
    betas=[]
    for d in y.index:
        df=pd.concat([y.loc[d].rename("y")]+[X[k].loc[d].rename(k) for k in X],axis=1).dropna()
        if len(df)<len(X)+8: continue
        Z=(df.drop(columns="y")-df.drop(columns="y").mean())/df.drop(columns="y").std(ddof=0).replace(0,np.nan)
        if Z.isna().any().any(): continue
        A=np.column_stack([np.ones(len(Z)),Z.values]); b=np.linalg.lstsq(A,df.y.values,rcond=None)[0]; betas.append(pd.Series(b,["const"]+list(X),name=d))
    B=pd.DataFrame(betas)
    if B.empty:
        names=["const"]+list(X)
        return pd.DataFrame(index=names,data={"mean":np.nan,"t_NW":np.nan}),B
    return pd.DataFrame({"mean":B.mean(),"t_NW":[newey_west_t(B[c],lags) for c in B]}),B
