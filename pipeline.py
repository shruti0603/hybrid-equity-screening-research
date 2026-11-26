import warnings; warnings.filterwarnings("ignore")
import numpy as np, pandas as pd
from pit import *
from sentiment import sentiment_asof
from backtest import *

GROWTH=[0.06,0.08,0.10,0.12,0.15]

def month_ends(prices, start, end):
    return pd.DatetimeIndex(prices.loc[start:end].resample("ME").last().index)

def build_panels(tickers, close, adjclose, splits, facts, news, start, end, window_days=30):
    """close: split-adjusted Close (date x ticker); adjclose: total-return adjusted close; splits: dict ticker->Series; facts: dict ticker->long df;
    news: DataFrame(ticker,ts,pc) or None. Returns dict of DataFrames (rebalance date x ticker)."""
    dates=[d for d in pd.date_range(start,end,freq="ME")]
    P={k:pd.DataFrame(index=dates,columns=tickers,dtype=float) for k in ["H","V","Vr","S","Sr","gap","fwd","mom","elig"]}
    mc=close.resample("ME").last().reindex(dates); ac=adjclose.resample("ME").last()
    fwd=(ac.shift(-1)/ac-1).reindex(dates); P["fwd"][:]=fwd[tickers].values
    mom=(ac.shift(1)/ac.shift(12)-1).reindex(dates); P["mom"][:]=mom[tickers].values   # 12-1 momentum, lagged one month
    cov=[]
    for d in dates:
        # Calendar month-end may be a weekend; last observed price is the actual rebalance date.
        trading_date=close.loc[:d].index[-1]
        asof=trading_date-pd.Timedelta(days=1)  # conservative one-day filing lag
        rows={};gaps={}
        for t in tickers:
            if t not in facts: continue
            s=pit_snapshot(facts[t],asof)
            if s is None or not np.isfinite(mc.loc[d,t]): continue
            rows[t]=health_raw(s); cov.append((d,t,s["debt_found"],np.isfinite(s["debt"]),np.isfinite(s["cash"]),np.isfinite(s["fcf"])))
            # Weighted-average diluted shares are an imperfect proxy for actual outstanding shares.
            # Historical split adjustment must stop at the trading date, NOT at the present.
            split_series=splits.get(t)
            split_factor=1.0 if split_series is None else float(split_series[(split_series.index>s["shares_filed"]) & (split_series.index<=trading_date)].prod())
            sh=s["shares_asreported"]*split_factor
            gs=[dcf_gap(s["fcf"],s["cash"],s["debt"],sh,mc.loc[d,t],g) for g in GROWTH]
            gaps[t]=np.nanmedian(gs) if np.isfinite(gs).any() else np.nan
        if len(rows)<10: continue
        rh=pd.DataFrame(rows).T; gp=pd.Series(gaps)
        sent=sentiment_asof(news,trading_date,window_days) if news is not None else pd.Series(dtype=float)
        sent=sent.reindex(rh.index)
        sc=build_scores(rh,gp.reindex(rh.index),sent)
        for k in ["H","V","Vr","S","Sr"]: P[k].loc[d,sc.index]=sc[k]
        P["gap"].loc[d,gp.index]=gp
    P["_cov"]=pd.DataFrame(cov,columns=["date","ticker","debt_found","debt_usable","cash_usable","fcf_usable"])
    return P

def analyze(P, outdir, cost_bps=10.0):
    import os; os.makedirs(outdir,exist_ok=True)
    fwd=P["fwd"].astype(float); comp={k:P[k].astype(float) for k in ["H","V","Vr","S","Sr"]}
    # COMMON SAMPLE: a firm-month enters only if health, sentiment AND valuation all exist, so ablations compare like with like
    has_s=bool(comp["S"].notna().any().any())            # False in LIGHT mode (no news): health + valuation only
    CMP=["H","S","V"] if has_s else ["H","V"]
    common=fwd.notna()
    for c in CMP: common=common&comp[c].notna()
    comp={k:v.where(common) for k,v in comp.items()}; mom=P["mom"].astype(float).where(common)
    pd.DataFrame({"names_in_common_sample":common.sum(axis=1),"names_with_health":P["H"].notna().sum(axis=1),"names_with_sentiment":P["S"].notna().sum(axis=1),"names_with_dcf":P["V"].notna().sum(axis=1)}).to_csv(f"{outdir}/diag_coverage_by_month.csv")
    if "_cov" in P: P["_cov"].groupby("ticker").debt_found.mean().rename("share_months_debt_tag_found").to_csv(f"{outdir}/diag_debt_tag_coverage.csv")
    # Independent H+V diagnostic: NOT a full-hybrid result and NOT a matched-sample ablation.
    hv_mask=fwd.notna() & P["H"].notna() & P["V"].notna()
    hv_score=(0.5*P["H"].astype(float)+0.2*P["V"].astype(float))/0.7
    hv_score=hv_score.where(hv_mask)
    hv_ic=monthly_ic(hv_score,fwd)
    hv_g,hv_n,hv_to=top_n_returns(hv_score,fwd,0.2,cost_bps)
    hv_perf=perf(hv_n)
    # Matched-sample equal-weight comparator: same months and eligible firms as H+V.
    # Only months where the H+V strategy can actually form a portfolio are retained.
    hv_ew=fwd.where(hv_mask).mean(axis=1).reindex(hv_n.index)
    hv_ew_perf=perf(hv_ew)
    pd.DataFrame({"H_V_net":hv_n,"H_V_gross":hv_g,"EW_same_eligible_firms":hv_ew,
                  "H_V_oneway_turnover":hv_to}).to_csv(f"{outdir}/returns_hv_matched_monthly.csv")
    pd.DataFrame([{"strategy":"H+V","CAGR_net":perf(hv_n)["CAGR"],"Sharpe_net":perf(hv_n)["Sharpe"],"MaxDD":perf(hv_n)["MaxDD"],"months":perf(hv_n)["N"]},
                  {"strategy":"EW on H+V eligible firms, same months","CAGR_net":hv_ew_perf["CAGR"],"Sharpe_net":hv_ew_perf["Sharpe"],"MaxDD":hv_ew_perf["MaxDD"],"months":hv_ew_perf["N"]}]).to_csv(f"{outdir}/table_hv_matched_comparison.csv",index=False)
    pd.DataFrame([block_boot_diff(hv_n,hv_ew)]).to_csv(f"{outdir}/table_hv_matched_sharpe_bootstrap.csv",index=False)
    pd.DataFrame([dict(strategy="H+V independently eligible (NOT full hybrid)",
        IC=hv_ic.mean(),IC_t_NW=newey_west_t(hv_ic),
        CAGR_gross=perf(hv_g)["CAGR"],CAGR_net=hv_perf["CAGR"],
        Sharpe_net=hv_perf["Sharpe"],MaxDD=hv_perf["MaxDD"],
        turnover=hv_to.mean(),months=hv_perf["N"])]).to_csv(
        f"{outdir}/table_hv_independent_diagnostic.csv",index=False)
    pd.DataFrame({"H_V_fwd_eligible":hv_mask.sum(axis=1),
        "H_S_V_fwd_eligible":common.sum(axis=1),
        "H_fwd_eligible":(P["H"].notna()&fwd.notna()).sum(axis=1),
        "V_fwd_eligible":(P["V"].notna()&fwd.notna()).sum(axis=1),
        "S_fwd_eligible":(P["S"].notna()&fwd.notna()).sum(axis=1)}).to_csv(
        f"{outdir}/diag_eligibility_detailed.csv")
    if has_s and int(common.sum(axis=1).max()) < 10:
        print("WARNING: Full H+S+V sample has fewer than 10 companies in every month; "
              "full-hybrid portfolio metrics cannot be estimated. "
              "H+V diagnostic is separate, not a substitute.",flush=True)

    if has_s:
        FULL="Full 50/30/20 (H,S,V)"
        W={FULL:{"H":.5,"S":.3,"V":.2},"Equal 1/3":{"H":1/3,"S":1/3,"V":1/3},
           "H only":{"H":1},"S only":{"S":1},"V only":{"V":1},"H+V":{"H":.5,"V":.5},"H+S":{"H":.5,"S":.5},"S+V":{"S":.5,"V":.5},
           "Full, rank variants (H,Sr,Vr)":{"H":.5,"Sr":.3,"Vr":.2},"V rank only":{"Vr":1}}
    else:
        FULL="Full H+V (0.5/0.2 renormalised; NO sentiment)"
        W={FULL:{"H":.5,"V":.2},"H only":{"H":1},"V only":{"V":1},"V rank only":{"Vr":1},"H + V rank":{"H":.5,"Vr":.2}}
    S=combos(comp,W); S["12-1 momentum"]=mom
    # same-sample rule: evaluate every strategy only on dates/names where the FULL score exists
    mask=common
    rows=[];nets={}
    for lab,sc in S.items():
        sc2=sc.where(mask)
        ic=monthly_ic(sc2,fwd); g,n,to=top_n_returns(sc2,fwd,0.2,cost_bps); nets[lab]=n
        p=perf(n); p0=perf(g)
        rows.append(dict(strategy=lab,IC=ic.mean(),IC_t_NW=newey_west_t(ic),hit=(ic>0).mean(),CAGR_gross=p0["CAGR"],CAGR_net=p["CAGR"],Sharpe_net=p["Sharpe"],MaxDD=p["MaxDD"],turnover=to.mean(),months=p["N"]))
    # Full-hybrid benchmark exists only in months where the full strategy is investable.
    investable=common.sum(axis=1)>=10
    ew=fwd.where(common).mean(axis=1).where(investable); nets["EW eligible universe"]=ew.dropna()
    rows.append({"strategy":"EW eligible universe",**{k:v for k,v in zip(["CAGR_net","Sharpe_net","MaxDD","months"],[perf(ew)["CAGR"],perf(ew)["Sharpe"],perf(ew)["MaxDD"],perf(ew)["N"]])}})
    T=pd.DataFrame(rows); T.to_csv(f"{outdir}/table_strategies.csv",index=False)
    full=nets[FULL]; bb={k:block_boot_diff(full,nets[k]) for k in ["EW eligible universe","12-1 momentum","H only","S only","V only","H+V"] if k in nets}
    pd.DataFrame(bb).T.to_csv(f"{outdir}/table_sharpe_diff_bootstrap.csv")
    # walk-forward weights
    wf,chosen=walk_forward_weights(CMP,comp,fwd)
    wf=wf.where(mask); g,n,to=top_n_returns(wf,fwd,0.2,cost_bps); icw=monthly_ic(wf,fwd)
    pd.DataFrame([dict(strategy="Walk-forward weights",IC=icw.mean(),IC_t_NW=newey_west_t(icw),**perf(n),turnover=to.mean())]).to_csv(f"{outdir}/table_walkforward.csv",index=False)
    chosen.to_csv(f"{outdir}/walkforward_chosen_weights.csv")
    # Fama-MacBeth
    fm,_=fama_macbeth(fwd,{**{c:comp[c] for c in CMP},"mom":mom}); fm.to_csv(f"{outdir}/table_fama_macbeth.csv")
    # DCF sign / uniform-overvaluation diagnostic
    gap=P["gap"].astype(float)
    denom=gap.notna().sum(axis=1).replace(0,np.nan)
    pd.DataFrame({"share_gap_negative":(gap<0).sum(axis=1)/denom,"median_gap":gap.median(axis=1)}).to_csv(f"{outdir}/diag_dcf_gap_by_month.csv")
    # decile-free subperiod robustness
    half=len(fwd)//2; sub=[]
    for lab in [l for l in [FULL,"H only","S only","V only","12-1 momentum"] if l in nets]:
        for nm,sl in [("first half",slice(0,half)),("second half",slice(half,None))]:
            r=nets[lab].iloc[sl]; sub.append(dict(strategy=lab,period=nm,**perf(r)))
    pd.DataFrame(sub).to_csv(f"{outdir}/table_subperiods.csv",index=False)
    cost=[]
    for bps in [0,10,25,50]:
        _,nn,_=top_n_returns(S[FULL].where(mask),fwd,0.2,bps); cost.append(dict(cost_bps=bps,**perf(nn)))
    pd.DataFrame(cost).to_csv(f"{outdir}/table_cost_sensitivity.csv",index=False)
    with open(f"{outdir}/results_tables.md","w",encoding="utf-8") as f:
        f.write("MODE: "+("FULL (health + sentiment + valuation)" if has_s else "LIGHT (health + valuation only; NO sentiment)")+"\n")
        for nm in ["table_strategies","table_sharpe_diff_bootstrap","table_walkforward","table_fama_macbeth","table_subperiods","table_cost_sensitivity"]:
            f.write(f"\n### {nm}\n\n"+pd.read_csv(f"{outdir}/{nm}.csv").round(4).to_markdown(index=False)+"\n")
    return T
