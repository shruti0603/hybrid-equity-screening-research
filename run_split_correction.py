"""IRFA split-basis CORRECTION run. OFFLINE and READ-ONLY on inputs: no downloads, no FinBERT scoring, no cache modification.
Steps: preflight -> automated split tests -> load caches -> CONTROL run (inputs exactly as before) -> CORRECTED run (Close converted to as-traded) ->
comparisons, valid sub-periods, effect statistics -> compact results ZIP. The pipeline code itself (pit.py, pipeline.py, backtest.py) is NOT modified."""
import sys; sys.dont_write_bytecode=True
import os, json, hashlib, glob, time, zipfile, argparse, platform, traceback, warnings, math
warnings.filterwarnings("ignore")
import numpy as np, pandas as pd
from scipy import stats
ROOT=os.getcwd(); sys.path.insert(0,ROOT)
ap=argparse.ArgumentParser(); ap.add_argument("--skip_tests",action="store_true"); ap.add_argument("--skip_control",action="store_true"); ap.add_argument("--start",default="2015-01-31"); ap.add_argument("--end",default="2023-12-31"); a=ap.parse_args()
T0=time.time(); LOG=[]
def log(*x):
    s=f"[{time.time()-T0:6.0f}s] "+" ".join(str(v) for v in x); print(s,flush=True); LOG.append(s)
def die(m): log("STOPPED:",m); open("correction_run_log.txt","w",encoding="utf-8").write("\n".join(LOG)); sys.exit(2)
KNOWN={"pit.py":"345b8a19cb7a4413","pipeline.py":"21f523609379e9e1","backtest.py":"dff471349aae98fa","sentiment.py":"fd6611b304fe1763"}   # hashes verified in the earlier verification runs
OUT0,OUT1="outputs_control_as_cached","outputs_split_corrected"; WORK="lowdisk_final"
# ---------------- preflight
log("PREFLIGHT")
need=["pit.py","pipeline.py","backtest.py","sentiment.py","universe_default.txt","split_fix.py","test_split_consistency.py",f"{WORK}/selected_news.parquet",f"{WORK}/finbert_parts/manifest.json","cache/sec","cache/prices"]
miss=[n for n in need if not os.path.exists(n)]
if miss: die("missing: "+", ".join(miss)+". Run this from the project folder that holds the final code, cache\\ and lowdisk_final\\ (the folder you ran final_lowdisk.py in).")
hashes={}
for f in KNOWN:
    h=hashlib.sha256(open(f,"rb").read()).hexdigest(); hashes[f]=h; log(f"  {f:14s} {h[:16]}", "(matches the verified version)" if h.startswith(KNOWN[f]) else "(DIFFERS from the verified version: the pipeline code changed since verification)")
def hash_inputs():
    d={}
    for p in sorted(glob.glob("cache/sec/*.json")+glob.glob("cache/prices/*.pkl")+glob.glob(f"{WORK}/finbert_parts/*")+[f"{WORK}/selected_news.parquet","universe_default.txt"]):
        if os.path.isfile(p):
            h=hashlib.sha256()
            with open(p,"rb") as fh:
                for b in iter(lambda:fh.read(1<<20),b""): h.update(b)
            d[p.replace("\\","/")]=h.hexdigest()
    return d
H_before=hash_inputs(); log("inputs hashed (before):",len(H_before),"files")
import pit, pipeline, backtest
from split_fix import to_as_traded, jump_table, clean_splits
# ---------------- automated tests
if not a.skip_tests:
    log("AUTOMATED SPLIT-CONSISTENCY TESTS (synthetic worlds; takes about a minute)")
    import test_split_consistency as T; res=T.run(); bad=[r for r in res if not r[1]]
    open("split_tests_report.txt","w",encoding="utf-8").write("\n".join(("PASS " if ok else "FAIL ")+n+(" - "+d if d else "") for n,ok,d in res)+f"\n\n{len(res)-len(bad)} of {len(res)} passed\n")
    if bad: die(f"{len(bad)} split-consistency test(s) failed; see split_tests_report.txt. Not running the experiments.")
    log(f"  {len(res)} of {len(res)} tests passed")
# ---------------- load caches (read-only), exactly as final_lowdisk.py does
tick=sorted(set(x.strip().upper() for x in open("universe_default.txt",encoding="utf-8").read().splitlines() if x.strip()))
facts={};C={};A={};spl={}
for t in tick:
    sf,pf=f"cache/sec/{t}.json",f"cache/prices/{t}.pkl"
    if not(os.path.isfile(sf) and os.path.isfile(pf)): continue
    with open(sf,encoding="utf-8") as f: facts[t]=pit.facts_to_df(json.load(f))
    h=pd.read_pickle(pf); C[t]=h["Close"]; A[t]=h["Adj Close"]; spl[t]=h["Stock Splits"][h["Stock Splits"]>0] if "Stock Splits" in h else pd.Series(dtype=float)
tk=list(facts)
if len(tk)<10: die("fewer than 10 tickers with both SEC and price caches")
close=pd.DataFrame(C); adj=pd.DataFrame(A); log("tickers loaded:",len(tk))
# ---------------- sentiment from the existing scored cache (never scores)
nf=pd.read_parquet(f"{WORK}/selected_news.parquet"); nf["ts"]=pd.to_datetime(nf.ts,utc=True).dt.tz_localize(None)
u=sorted(nf.headline.dropna().unique()); meta=json.load(open(f"{WORK}/finbert_parts/manifest.json",encoding="utf-8"))
if meta.get("sig")!=hashlib.md5("\n".join(u).encode("utf-8")).hexdigest() or meta.get("n")!=len(u): die("scored-sentiment cache does not match selected_news.parquet (signature mismatch). Refusing to rescore.")
size=int(meta.get("part_size",5000)); parts=[]
for i in range((len(u)+size-1)//size):
    p=f"{WORK}/finbert_parts/part_{i:05d}.parquet"
    if not os.path.isfile(p): die("missing cached FinBERT part: "+p+" (this run never scores)")
    parts.append(pd.read_parquet(p))
pc=pd.concat(parts,ignore_index=True)
if pc.headline.duplicated().any() or set(pc.headline)!=set(u): die("cached FinBERT headlines do not match")
news=nf[["ticker","ts"]].copy(); news["pc"]=nf.headline.map(pc.set_index("headline").pc)
if news.pc.isna().any(): die("unscored headlines present")
log("cached sentiment loaded: unique headlines",len(u),"| rows",len(news),"| NO rescoring")
# ---------------- price-basis gate
at=to_as_traded(close,spl); jc=jump_table({t:close[t] for t in close.columns},spl); ja=jump_table({t:at[t] for t in at.columns},spl)
jc.to_csv("price_basis_cached_close_jumps.csv",index=False); ja.to_csv("price_basis_corrected_close_jumps.csv",index=False)
log(f"  cached Close, discriminating split events (|ln ratio|>0.25): {len(jc)}; verdicts {jc.looks.value_counts().to_dict()}")
log(f"  corrected Close, same events: verdicts {ja.looks.value_counts().to_dict()}")
if len(ja) and not (ja.looks=="as-traded").all(): die("the corrected series still shows split jumps that do not match the split ratios; see price_basis_corrected_close_jumps.csv")
for t,d0,known in (("AAPL","2020-08-28",499.23),("TSLA","2020-08-28",2213.40)):   # informational anchors only (well-known closes, from memory)
    if t in at.columns and pd.Timestamp(d0) in at.index: log(f"  anchor {t} {d0}: reconstructed as-traded close = {at.loc[pd.Timestamp(d0),t]:.2f} (publicly reported about {known}; informational)")
# ---------------- runs
def run(tag,close_in,outdir):
    log(f"{tag}: build_panels"); P=pipeline.build_panels(tk,close_in,adj,spl,facts,news,a.start,a.end); os.makedirs(outdir,exist_ok=True)
    log(f"{tag}: analyze (tests, bootstrap, walk-forward, Fama-MacBeth)"); Tbl=pipeline.analyze(P,outdir,cost_bps=10); log(f"{tag}: done"); return P
P0=None if a.skip_control else run("CONTROL (cached Close as before)",close,OUT0)
P1=run("CORRECTED (as-traded Close)",at,OUT1)
# ---------------- helpers
def extract(d):
    r={}
    f=lambda n:pd.read_csv(f"{d}/{n}")
    h=f("table_hv_independent_diagnostic.csv").iloc[0]; r["H+V (own sample): net CAGR"]=h.CAGR_net; r["H+V: net Sharpe"]=h.Sharpe_net; r["H+V: max drawdown"]=h.MaxDD; r["H+V: mean IC"]=h.IC; r["H+V: NW t(IC)"]=h.IC_t_NW; r["H+V: months"]=h.months; r["H+V: mean turnover"]=h.turnover; r["H+V: gross CAGR"]=h.CAGR_gross
    m=f("table_hv_matched_comparison.csv"); r["EW same firms: net CAGR"]=m.iloc[1].CAGR_net; r["EW same firms: Sharpe"]=m.iloc[1].Sharpe_net; r["EW same firms: max drawdown"]=m.iloc[1].MaxDD
    b=f("table_hv_matched_sharpe_bootstrap.csv").iloc[0]; r["Sharpe diff H+V - EW"]=b["diff"]; r["Sharpe diff lo"]=b["lo"]; r["Sharpe diff hi"]=b["hi"]
    s=f("table_strategies.csv")
    for _,x in s.iterrows():
        r[f"[H,S,V sample] {x.strategy}: months"]=x.months; r[f"[H,S,V sample] {x.strategy}: net CAGR"]=x.CAGR_net; r[f"[H,S,V sample] {x.strategy}: net Sharpe"]=x.Sharpe_net
        if pd.notna(x.get("IC",np.nan)): r[f"[H,S,V sample] {x.strategy}: mean IC"]=x.IC; r[f"[H,S,V sample] {x.strategy}: NW t(IC)"]=x.IC_t_NW
    return r
def same(a_,b_): return bool(np.array_equal(np.isnan(a_.values.astype(float)),np.isnan(b_.values.astype(float))) and np.allclose(np.nan_to_num(a_.values.astype(float),nan=-9),np.nan_to_num(b_.values.astype(float),nan=-9),rtol=1e-12,atol=1e-12))
prev=json.load(open("previous_reported_values.json"))
rows=[]; R1=extract(OUT1); R0=extract(OUT0) if P0 is not None else {}
pmap={"H+V (own sample): net CAGR":prev["hv_independent"]["CAGR_net"],"H+V: net Sharpe":prev["hv_independent"]["Sharpe_net"],"H+V: max drawdown":prev["hv_independent"]["MaxDD"],"H+V: mean IC":prev["hv_independent"]["IC"],"H+V: NW t(IC)":prev["hv_independent"]["IC_t_NW"],"H+V: months":prev["hv_independent"]["months"],"H+V: mean turnover":prev["hv_independent"]["turnover"],"H+V: gross CAGR":prev["hv_independent"]["CAGR_gross"],
 "EW same firms: net CAGR":prev["hv_matched_ew"]["CAGR_net"],"EW same firms: Sharpe":prev["hv_matched_ew"]["Sharpe_net"],"EW same firms: max drawdown":prev["hv_matched_ew"]["MaxDD"],"Sharpe diff H+V - EW":prev["hv_bootstrap"].get("diff"),"Sharpe diff lo":prev["hv_bootstrap"].get("lo"),"Sharpe diff hi":prev["hv_bootstrap"].get("hi")}
for st,v in prev["strategies"].items():
    for k,lab in (("months","months"),("CAGR_net","net CAGR"),("Sharpe_net","net Sharpe"),("IC","mean IC"),("IC_t_NW","NW t(IC)")):
        if v.get(k) is not None: pmap[f"[H,S,V sample] {st}: {lab}"]=v[k]
for k in R1:
    pv=pmap.get(k); c0=R0.get(k); c1=R1[k]
    rows.append(dict(metric=k,previous_run_pre_correction=pv,control_rerun_as_before=c0,corrected=c1,control_reproduces_previous=(None if pv is None or c0 is None else bool(abs(float(c0)-float(pv))<=1e-8*max(1,abs(float(pv))))),corrected_minus_previous=(None if pv is None else float(c1)-float(pv))))
CMP=pd.DataFrame(rows); CMP.to_csv("comparison_control_vs_corrected.csv",index=False)
if P0 is not None:
    chk=CMP.dropna(subset=["control_reproduces_previous"]); n_ok=int(chk.control_reproduces_previous.sum()); log(f"CONTROL reproduces the earlier reported figures: {n_ok} of {len(chk)} metrics match to 1e-8")
# ---- effect of the correction on the panels
eff={}
if P0 is not None:
    eff["panels_identical_H_S_Sr_fwd_mom"]={k:same(P0[k],P1[k]) for k in ("H","S","Sr","fwd","mom")}
    eff["V_availability_identical"]=bool(np.array_equal(P0["V"].astype(float).notna().values,P1["V"].astype(float).notna().values))
    g0,g1=P0["gap"].astype(float),P1["gap"].astype(float); both=g0.notna()&g1.notna(); diff=(g0-g1).abs()>1e-9; aff=both&diff
    eff["valuation_firm_months"]=int(both.sum().sum()); eff["firm_months_changed"]=int(aff.sum().sum()); eff["share_changed"]=float(aff.sum().sum()/max(both.sum().sum(),1))
    eff["firms_changed"]=sorted(g0.columns[aff.any(axis=0)].tolist())
    if aff.values.any():
        a0,a1=g0.values[aff.values],g1.values[aff.values]; eff["median_gap_changed_control"]=float(np.median(a0)); eff["median_gap_changed_corrected"]=float(np.median(a1))
        eff["V_pinned_at_100_changed_control"]=float(np.mean((100+a0)>=100)); eff["V_pinned_at_100_changed_corrected"]=float(np.mean((100+a1)>=100))
    cs=[]
    for d in g0.index:
        m=both.loc[d]
        if m.sum()>=10: cs.append(stats.spearmanr((100+g0.loc[d][m]).clip(0,100),(100+g1.loc[d][m]).clip(0,100))[0])
    eff["monthly_spearman_V_control_vs_corrected_median"]=float(np.nanmedian(cs)) if cs else None; eff["monthly_spearman_V_min"]=float(np.nanmin(cs)) if cs else None
    gm0,gm1=g0.median(axis=1),g1.median(axis=1); eff["months_positive_median_gap_control"]=int((gm0>0).sum()); eff["months_positive_median_gap_corrected"]=int((gm1>0).sum())
    pd.DataFrame({"median_gap_control":gm0,"median_gap_corrected":gm1,"share_negative_control":(g0<0).sum(axis=1)/g0.notna().sum(axis=1),"share_negative_corrected":(g1<0).sum(axis=1)/g1.notna().sum(axis=1)}).to_csv("dcf_gap_control_vs_corrected_by_month.csv")
json.dump(eff,open("split_correction_effect.json","w"),indent=1,default=str)
# ---- valid sub-period tables (the pipeline's own table_subperiods.csv is invalid: its split is positional on the full index)
def valid_subperiods(P,outdir):
    try:
        bt=backtest; fwd=P["fwd"].astype(float); comp={k:P[k].astype(float) for k in ["H","V","Vr","S","Sr"]}
        common=fwd.notna()&comp["H"].notna()&comp["S"].notna()&comp["V"].notna(); comp={k:v.where(common) for k,v in comp.items()}; mom=P["mom"].astype(float).where(common)
        W={"Full 50/30/20 (H,S,V)":{"H":.5,"S":.3,"V":.2},"H only":{"H":1},"S only":{"S":1},"V only":{"V":1},"H+V":{"H":.5,"V":.5}}
        S=bt.combos(comp,W); S["12-1 momentum"]=mom; nets={lab:bt.top_n_returns(sc.where(common),fwd,0.2,10)[1] for lab,sc in S.items()}
        nets["EW eligible universe"]=fwd.where(common).mean(axis=1).where(common.sum(axis=1)>=10).dropna()
        ref=pd.read_csv(f"{outdir}/table_strategies.csv").set_index("strategy").CAGR_net; fl="Full 50/30/20 (H,S,V)"
        if abs(bt.perf(nets[fl])["CAGR"]-ref[fl])>1e-10: return "replication mismatch with table_strategies.csv; sub-period table not produced"
        rows=[]
        for lab,r in nets.items():
            r=r.dropna(); k=len(r)//2
            for nm,x in (("first half of evaluable months",r.iloc[:k]),("second half of evaluable months",r.iloc[k:])):
                if len(x)>=3: rows.append(dict(sample="H,S,V common sample",strategy=lab,period=nm,first=x.index[0].date(),last=x.index[-1].date(),**bt.perf(x)))
        hv=pd.read_csv(f"{outdir}/returns_hv_matched_monthly.csv",index_col=0,parse_dates=True)
        for col in ("H_V_net","EW_same_eligible_firms"):
            for nm,x in (("2015-2019",hv[col][:"2019-12-31"]),("2020-2023",hv[col]["2020-01-01":])):
                if len(x)>=3: rows.append(dict(sample="H+V own sample",strategy=col,period=nm,first=x.index[0].date(),last=x.index[-1].date(),**bt.perf(x)))
        pd.DataFrame(rows).to_csv(f"{outdir}/table_subperiods_valid.csv",index=False); return "ok"
    except Exception as e: return f"failed: {type(e).__name__}: {str(e)[:120]}"
log("valid sub-period table (corrected run):",valid_subperiods(P1,OUT1))
if P0 is not None: log("valid sub-period table (control run):",valid_subperiods(P0,OUT0))
# ---------------- read-only proof, manifests, summary, zip
H_after=hash_inputs(); changed=[k for k in set(H_before)|set(H_after) if H_before.get(k)!=H_after.get(k)]; log("READ-ONLY CHECK: inputs unchanged =",not changed)
json.dump(dict(inputs_before=H_before,inputs_unchanged=not changed,code_hashes=hashes,python=platform.python_version(),pandas=pd.__version__,numpy=np.__version__,start=a.start,end=a.end,tickers=tk,downloaded=False,finbert_scored=False,
   correction="close converted to as-traded: Close x product of split ratios with ex-date after each date; shares multiplied by splits in (filing date, trading date] as in the final build_panels; pipeline code unmodified",version="split-correction-2026-11-21"),open("correction_manifest.json","w"),indent=1)
def S(d,k,default="n/a"):
    try: return d.get(k,default)
    except Exception: return default
with open("correction_summary.md","w",encoding="utf-8") as f:
    f.write("# Split-basis correction: summary\n\nCorrected run = cached Close converted to as-traded prices; pipeline code unchanged. All figures below are recomputed; the 'previous run' column exists only to test reproduction.\n\n")
    f.write(CMP.round(5).to_markdown(index=False)+"\n\n## Effect on valuation\n\n```\n"+json.dumps(eff,indent=1,default=str)+"\n```\n")
z="UPLOAD_ME_split_corrected_results.zip"
with zipfile.ZipFile(z,"w",zipfile.ZIP_DEFLATED) as zf:
    for d in (OUT1,OUT0):
        for p in glob.glob(f"{d}/*"):
            if os.path.isfile(p) and p.lower().endswith((".csv",".md")): zf.write(p)
    for p in ("comparison_control_vs_corrected.csv","dcf_gap_control_vs_corrected_by_month.csv","split_correction_effect.json","correction_manifest.json","correction_summary.md","split_tests_report.txt","price_basis_cached_close_jumps.csv","price_basis_corrected_close_jumps.csv"):
        if os.path.isfile(p): zf.write(p)
    open("correction_run_log.txt","w",encoding="utf-8").write("\n".join(LOG)); zf.write("correction_run_log.txt")
log("DONE. Upload",os.path.abspath(z))
