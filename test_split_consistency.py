"""Automated tests of split-adjustment consistency, run against YOUR pit.py/pipeline.py on tiny synthetic worlds (no real data).
World A: a firm that never splits. World B: the SAME firm economics with a split (or spin-off-style factor, or reverse split) and a cache Close that is
retroactively split-adjusted, exactly like the vendor cache. Correct handling must give the same DCF gap in both worlds at every date."""
import sys; sys.dont_write_bytecode=True
import os, numpy as np, pandas as pd, traceback, warnings; warnings.filterwarnings("ignore")
sys.path.insert(0,os.getcwd()); import pit, pipeline
from split_fix import to_as_traded, jump_table
START,END="2018-01-31","2020-12-31"
def mk_facts(shares_fn):
    rows=[]
    for y in range(2012,2024):
        end=pd.Timestamp(f"{y}-12-31"); st=pd.Timestamp(f"{y}-01-01"); fl=pd.Timestamp(f"{y+1}-02-15"); base=1e10*(1.05**(y-2011))
        for tag,v in [("Revenues",base),("NetIncomeLoss",base*.1),("NetCashProvidedByUsedInOperatingActivities",base*.15),("PaymentsToAcquirePropertyPlantAndEquipment",base*.03),("WeightedAverageNumberOfDilutedSharesOutstanding",shares_fn(fl))]: rows.append((tag,st,end,v,fl,"10-K","FY"))
        for tag,v in [("StockholdersEquity",base*.8),("CashAndCashEquivalentsAtCarryingValue",base*.3),("LongTermDebt",1e9*(1.05**(y-2011)))]: rows.append((tag,pd.NaT,end,v,fl,"10-K","FY"))
    return pd.DataFrame(rows,columns=["tag","start","end","val","filed","form","fp"])
def world(events, n=10, seed=11):
    """events: list of (ex_date, ratio) for ticker T00 only. Returns dict with traded prices of A, cache Close of B (adjusted), splits, facts for both worlds."""
    rng=np.random.default_rng(seed); T=[f"T{i:02d}" for i in range(n)]; idx=pd.bdate_range("2012-01-02","2024-03-29")
    PA=pd.DataFrame({t:100*np.exp(np.cumsum(rng.normal(3e-4,0.015,len(idx)))) for t in T},index=idx)
    ev=sorted((pd.Timestamp(d),float(r)) for d,r in events); upto=lambda d:float(np.prod([r for e,r in ev if e<=d])) if ev else 1.0
    cumup=pd.Series([upto(d) for d in idx],index=idx); R=float(np.prod([r for _,r in ev])) if ev else 1.0
    PB=PA.copy(); PB["T00"]=PA["T00"]/cumup                     # as-traded price in world B
    CB=PA.copy(); CB["T00"]=PA["T00"]/R                         # cache Close in world B: retroactively adjusted for ALL splits
    spl={t:pd.Series(dtype=float,index=pd.DatetimeIndex([])) for t in T}; spl["T00"]=pd.Series([r for _,r in ev],index=pd.DatetimeIndex([e for e,_ in ev]))
    fA={t:mk_facts(lambda fl:1e9) for t in T}; fB=dict(fA); fB["T00"]=mk_facts(lambda fl:1e9*upto(fl))
    return dict(T=T,PA=PA,PB=PB,CB=CB,spl=spl,fA=fA,fB=fB)
def gap(close,adj,spl,facts,T):
    P=pipeline.build_panels(T,close,adj,spl,facts,None,START,END); return P
def run():
    res=[]; 
    def rec(name,ok,detail=""): res.append((name,bool(ok),detail)); print(("PASS " if ok else "FAIL ")+name+(" - "+detail if detail else ""),flush=True)
    cases={"4:1 forward split (2019-06-03)":[("2019-06-03",4.0)],"spin-off-style factor 1.324 (2018-05-15)":[("2018-05-15",1.324)],"1:8 reverse split (2020-09-01)":[("2020-09-01",0.125)],"two splits 2:1 (2018-03-01) and 3:1 (2020-04-01)":[("2018-03-01",2.0),("2020-04-01",3.0)]}
    for nm,ev in cases.items():
        try:
            w=world(ev); T=w["T"]; PA=pipeline.build_panels(T,w["PA"],w["PA"],w["spl"] if False else {t:pd.Series(dtype=float,index=pd.DatetimeIndex([])) for t in T},w["fA"],None,START,END)
            tradedB=to_as_traded(w["CB"],w["spl"])
            rec(f"[{nm}] round trip: to_as_traded(adjusted Close) recovers the true as-traded price",np.allclose(tradedB["T00"].values,w["PB"]["T00"].values,rtol=1e-12))
            Pc=pipeline.build_panels(T,tradedB,w["CB"],w["spl"],w["fB"],None,START,END)    # CORRECTED inputs
            P0=pipeline.build_panels(T,w["CB"],w["CB"],w["spl"],w["fB"],None,START,END)     # AS CACHED (defect)
            gA=PA["gap"].astype(float)["T00"]; gC=Pc["gap"].astype(float)["T00"]; g0=P0["gap"].astype(float)["T00"]; ok=gA.notna()&gC.notna()
            rec(f"[{nm}] corrected gap equals the no-split world at every month ({int(ok.sum())} months)",ok.sum()>=30 and np.nanmax(np.abs(gA[ok]-gC[ok]))<1e-8,f"max |diff| = {np.nanmax(np.abs(gA[ok]-gC[ok])):.2e}")
            first=min(pd.Timestamp(d) for d,_ in ev); pre=(gA.index<first)&gA.notna()&g0.notna(); fac=float(np.prod([r for _,r in ev])); ratio=((1+g0[pre]/100)/(1+gA[pre]/100)) if pre.any() else pd.Series([np.nan])
            rec(f"[{nm}] test is sensitive: the AS-CACHED path overstates (1+gap) by the split factor before the first split",pre.any() and np.allclose(ratio.values,fac,rtol=1e-6),f"expected factor {fac:g}, observed {float(ratio.median()):.4g}")
            others=[t for t in T if t!="T00"]
            rec(f"[{nm}] returns, momentum and health are identical between as-cached and corrected runs",all(np.allclose(P0[k].astype(float).fillna(-9).values,Pc[k].astype(float).fillna(-9).values) for k in ("fwd","mom","H")))
            rec(f"[{nm}] non-split firms' valuation gaps are unchanged by the correction",np.allclose(P0["gap"].astype(float)[others].fillna(-9).values,Pc["gap"].astype(float)[others].fillna(-9).values))
            j1=jump_table({"T00":tradedB["T00"]},w["spl"]); j0=jump_table({"T00":w["CB"]["T00"]},w["spl"])
            if len(j1): rec(f"[{nm}] data-driven gate: corrected series jumps by the split ratio, cached series does not",(j1.looks=="as-traded").all() and (j0.looks=="adjusted").all())
        except Exception as e: rec(f"[{nm}] test errored",False,type(e).__name__+": "+str(e)[:160]); print(traceback.format_exc()[-500:])
    try:   # splits that occurred BEFORE every filing used must change nothing
        w=world([("2012-06-01",4.0)]); T=w["T"]; tb=to_as_traded(w["CB"],w["spl"]); PA=pipeline.build_panels(T,w["PA"],w["PA"],{t:pd.Series(dtype=float,index=pd.DatetimeIndex([])) for t in T},w["fA"],None,START,END)
        Pc=pipeline.build_panels(T,tb,w["CB"],w["spl"],w["fB"],None,START,END); a=PA["gap"].astype(float)["T00"]; b=Pc["gap"].astype(float)["T00"]; ok=a.notna()&b.notna()
        rec("[split before the sample] no double counting: corrected gap equals the no-split world",ok.sum()>=30 and np.nanmax(np.abs(a[ok]-b[ok]))<1e-8)
    except Exception as e: rec("[split before the sample] errored",False,str(e)[:160])
    return res
if __name__=="__main__":
    r=run(); bad=[x for x in r if not x[1]]; print(f"\n{len(r)-len(bad)} of {len(r)} tests passed"); sys.exit(1 if bad else 0)
