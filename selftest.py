"""SYNTHETIC smoke/regression tests (random data; NOT research results). Each test targets a failure mode real data would expose."""
import numpy as np, pandas as pd, os, shutil, tempfile, json
from pit import *; from pipeline import *; import sentiment as sn
from run_all import prepare_news
rng=np.random.default_rng(1); T=[f"T{i:02d}" for i in range(40)]
idx=pd.bdate_range("2012-01-02","2024-03-31"); n=len(idx)
close=pd.DataFrame({t:100*np.exp(np.cumsum(rng.normal(3e-4,0.015,n))) for t in T},index=idx); adj=close.copy()
spl={t:pd.Series(dtype=float) for t in T}; spl["T00"]=pd.Series([4.0],index=[pd.Timestamp("2019-06-03")])
def mk(t,i,rev_switch=False):
    rows=[]; base=1e9*(1+i%5)
    for fy in range(2011,2024):
        end=pd.Timestamp(f"{fy}-12-31"); st=pd.Timestamp(f"{fy}-01-01"); fl=end+pd.Timedelta(days=50); g=1.1**(fy-2011)
        rt="Revenues" if not(rev_switch and fy>=2018) else "RevenueFromContractWithCustomerExcludingAssessedTax"
        for tag,v in [(rt,base*g*10),("NetIncomeLoss",base*g*1.2),("NetCashProvidedByUsedInOperatingActivities",base*g*1.5),("PaymentsToAcquirePropertyPlantAndEquipment",base*g*0.3)]:
            rows.append((tag,st,end,v,fl,"10-K","FY"))
        for tag,v in [("StockholdersEquity",base*g*8),("LongTermDebt",base*g*2),("LongTermDebtCurrent",base*g*0.5),("CashAndCashEquivalentsAtCarryingValue",base*g*3)]:
            rows.append((tag,None,end,v,fl,"10-K","FY"))
        shv=4e9 if (t=="T00" and fl>=pd.Timestamp("2019-06-03")) else 1e9
        rows.append(("WeightedAverageNumberOfDilutedSharesOutstanding",st,end,shv,fl,"10-K","FY"))
    df=pd.DataFrame(rows,columns=["tag","start","end","val","filed","form","fp"])
    for c in("start","end","filed"): df[c]=pd.to_datetime(df[c])
    return df
facts={t:mk(t,i,rev_switch=(t=="T01")) for i,t in enumerate(T)}
# 1 split consistency
s=pit_snapshot(facts["T00"],pd.Timestamp("2018-12-31")); f=split_factor_after(spl["T00"],s["shares_filed"]); assert f==4.0
a=dcf_gap(s["fcf"],s["cash"],s["debt"],s["shares_asreported"]*f,close.loc["2018-12-31","T00"],0.10); b=dcf_gap(s["fcf"],s["cash"],s["debt"],s["shares_asreported"],close.loc["2018-12-31","T00"]*4,0.10)
assert abs(a-b)<1e-9; print("1 split consistency ok")
# 2 filing-date point-in-time
assert pit_snapshot(facts["T05"],pd.Timestamp("2024-01-30"))["fye"]==pd.Timestamp("2022-12-31"); print("2 point-in-time filing ok")
# 3 revenue tag switch (ASC 606): must NOT freeze on the old tag
assert pit_snapshot(facts["T01"],pd.Timestamp("2023-06-30"))["fye"]==pd.Timestamp("2022-12-31"); print("3 revenue tag switch ok")
# 4 debt not double counted
sd=pit_snapshot(facts["T05"],pd.Timestamp("2023-06-30")); base=1e9*(1+5%5); assert abs(sd["debt"]-base*1.1**11*2)<1; print("4 debt double-count ok")
# 5 missing capex -> FCF NaN (never assumed 0)
fx=facts["T07"]; fx=fx[fx.tag!="PaymentsToAcquirePropertyPlantAndEquipment"]; assert np.isnan(pit_snapshot(fx,pd.Timestamp("2023-06-30"))["fcf"]); print("5 missing-capex ok")
# 6 stale guard
assert pit_snapshot(facts["T05"],pd.Timestamp("2030-01-01")) is None; print("6 stale guard ok")
# 7 checkpoint resume
d=tempfile.mkdtemp(); hs=[f"headline {i} earnings" for i in range(23)]; calls=[]
def fake(chunk):
    calls.append(len(chunk))
    if len(calls)==3 and not os.path.exists(d+"/ok"): raise KeyboardInterrupt("simulated crash")
    return pd.DataFrame({"label":["positive"]*len(chunk),"conf":[0.9]*len(chunk)})
try: sn.score_unique(hs,d+"/p",scorer=fake,part_size=5,log=lambda *a:None)
except KeyboardInterrupt: pass
open(d+"/ok","w").write("1"); calls.clear(); r=sn.score_unique(hs,d+"/p",scorer=fake,part_size=5,log=lambda *a:None)
assert len(r)==23 and calls==[5,5,3] and abs(r.iloc[0]-0.9)<1e-9, calls; print("7 checkpoint resume ok (only unfinished parts rescored)")
try: sn.score_unique(hs[:-1],d+"/p",scorer=fake,part_size=5,log=lambda *a:None); raise SystemExit("stale checkpoint not detected")
except RuntimeError: print("  stale-checkpoint guard ok")
# 8 chunked FNSPID-style CSV: quotes, commas, newlines, unicode, tz suffix, bad ticker case
csv=d+"/news.csv"; rows=[]
for i in range(60):
    rows.append({"Date":f"2020-0{1+i%9}-1{i%9} 1{i%9}:00:00 UTC","Article_title":f'Nestlé "profit" beat, stock up {i}',"Stock_symbol":["T00","t01","ZZZ"][i%3],"Article":"line1\nline2, with comma"})
pd.DataFrame(rows).to_csv(csv,index=False,encoding="utf-8")
nf=prepare_news(csv,["T00","T01"],"2020-01-31","2020-12-31",5,d+"/c",chunk=7); assert set(nf.ticker)=={"T00","T01"} and nf.groupby(["ticker",nf.ts.dt.to_period("M")]).size().max()<=5; print("8 FNSPID chunked reader ok",len(nf),"rows")
# 9 end-to-end + common-sample rule
news=pd.DataFrame({"ticker":rng.choice(T[:20],200000),"ts":pd.to_datetime(rng.integers(pd.Timestamp("2012-01-01").value,pd.Timestamp("2024-03-01").value,200000)),"pc":rng.uniform(-1,1,200000)})
P=build_panels(T,close,adj,spl,facts,news,"2015-01-31","2023-12-31"); T1=analyze(P,d+"/out")
cs=pd.read_csv(d+"/out/diag_coverage_by_month.csv"); assert cs.names_in_common_sample.max()<=20, cs.names_in_common_sample.max(); print("9 common-sample rule ok (max",cs.names_in_common_sample.max(),"names; sentiment exists for 20)")
print(T1.round(3).to_string()); print("ALL SELF-TESTS PASSED")
# 10 JSONL news reader + LIGHT mode (no sentiment) analysis path
jl=d+"/news.jsonl"; pd.DataFrame(rows).to_json(jl,orient="records",lines=True,force_ascii=False)
nf2=prepare_news(jl,["T00","T01"],"2020-01-31","2020-12-31",5,d+"/c2",chunk=7); assert set(nf2.ticker)=={"T00","T01"}; print("10 JSONL reader ok",len(nf2),"rows")
P2=build_panels(T,close,adj,spl,facts,None,"2015-01-31","2023-12-31"); T2=analyze(P2,d+"/out_light"); assert "Full H+V (0.5/0.2 renormalised; NO sentiment)" in set(T2.strategy); print("11 LIGHT mode ok:",list(T2.strategy))
print("ALL SELF-TESTS PASSED (incl. light mode)")
