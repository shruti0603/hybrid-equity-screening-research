"""Recomputes the Experiment 1 statistics and the implied IC standard errors from the supplied outputs (read-only). Run: python verify_results.py"""
import pandas as pd, numpy as np, os
O=os.path.join(os.path.dirname(os.path.abspath(__file__)),"outputs")
r=pd.read_csv(f"{O}/returns_hv_matched_monthly.csv",index_col=0,parse_dates=True); a,b=r.H_V_net,r.EW_same_eligible_firms
def perf(x):
    c=(1+x).prod()**(12/len(x))-1; sh=x.mean()/x.std(ddof=1)*np.sqrt(12); cum=(1+x).cumprod(); return dict(CAGR=c,vol=x.std(ddof=1)*np.sqrt(12),Sharpe=sh,MaxDD=(cum/cum.cummax()-1).min(),months=len(x))
print("H+V net",{k:round(v,4) for k,v in perf(a).items()}); print("EW same firms",{k:round(v,4) for k,v in perf(b).items()})
def sh(v): return v.mean()/v.std(ddof=1)*np.sqrt(12)
A=np.column_stack([a.values,b.values]); n=len(A); rng=np.random.default_rng(0); out=[]
for _ in range(5000):
    st=rng.integers(0,n,int(np.ceil(n/6))); ix=np.concatenate([(s+np.arange(6))%n for s in st])[:n]; x=A[ix]; out.append(sh(x[:,0])-sh(x[:,1]))
out=np.array(out); print("bootstrap Sharpe diff",round(out.mean(),4),np.round(np.percentile(out,[2.5,97.5]),4),"P(<=0)",(out<=0).mean())
d=a-b; print("mean monthly diff",round(d.mean(),5),"simple t",round(d.mean()/(d.std(ddof=1)/np.sqrt(len(d))),2))
X=np.column_stack([np.ones(n),b.values]); co=np.linalg.lstsq(X,a.values,rcond=None)[0]; e=a.values-X@co; cov=(e@e/(n-2))*np.linalg.inv(X.T@X); print("alpha",round(co[0],5),"t",round(co[0]/np.sqrt(cov[0,0]),2),"beta",round(co[1],3))
t=pd.read_csv(f"{O}/table_strategies.csv").dropna(subset=["IC"]); t["se_IC"]=(t.IC/t.IC_t_NW).abs(); print(t[["strategy","IC","IC_t_NW","se_IC"]].round(4).to_string(index=False)); print("mean SE",round(t.se_IC.mean(),4),"approx minimal detectable IC (80% power)",round(2.8*t.se_IC.mean(),3))
