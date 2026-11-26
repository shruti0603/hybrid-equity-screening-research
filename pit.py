"""Point-in-time accounting + split-consistent DCF + signals. Every input is timestamped by SEC `filed` date."""
import numpy as np, pandas as pd

FLOW = {"rev":["Revenues","RevenueFromContractWithCustomerExcludingAssessedTax","SalesRevenueNet","RevenueFromContractWithCustomerIncludingAssessedTax"],
        "ni":["NetIncomeLoss","ProfitLoss"],"cfo":["NetCashProvidedByUsedInOperatingActivities"],
        "capex":["PaymentsToAcquirePropertyPlantAndEquipment","PaymentsToAcquireProductiveAssets","PaymentsForCapitalImprovements"]}
INST = {"cash_all":["CashCashEquivalentsAndShortTermInvestments"],"cash":["CashAndCashEquivalentsAtCarryingValue"],
        "sti":["MarketableSecuritiesCurrent","ShortTermInvestments","AvailableForSaleSecuritiesDebtSecuritiesCurrent"],
        "debt_total":["LongTermDebt"],"debt_nc":["LongTermDebtNoncurrent"],"debt_c":["LongTermDebtCurrent","DebtCurrent"],
        "eq":["StockholdersEquity","StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest"]}
SHARES = ["WeightedAverageNumberOfDilutedSharesOutstanding","WeightedAverageNumberOfSharesOutstandingBasic"]
KEEP_TAGS = set(sum(FLOW.values(),[])+sum(INST.values(),[])+SHARES)
MAX_STALE_DAYS = 540   # skip a firm-month if the latest fiscal year-end is older than this

def facts_to_df(cf):
    """SEC companyfacts JSON -> long df restricted to the tags we use (keeps memory small and lookups fast)."""
    rows=[]
    for tag,d in cf.get("facts",{}).get("us-gaap",{}).items():
        if tag not in KEEP_TAGS: continue
        for unit,items in d.get("units",{}).items():
            if unit not in ("USD","shares"): continue
            for it in items:
                rows.append((tag,it.get("start"),it["end"],it["val"],it["filed"],it.get("form"),it.get("fp")))
    df=pd.DataFrame(rows,columns=["tag","start","end","val","filed","form","fp"])
    for c in ("start","end","filed"): df[c]=pd.to_datetime(df[c])
    return df

def _union(k, tags):
    """All rows for any tag in `tags` (priority = list order). Handles firms that switch tags over time (e.g. ASC 606 in 2018)."""
    parts=[]
    for pr,t in enumerate(tags):
        s=k[k.tag==t]
        if len(s): parts.append(s.assign(prio=pr))
    return pd.concat(parts) if parts else k.iloc[0:0].assign(prio=0)

def _is_fy(s): return (s.end-s.start).dt.days.between(350,380)

def _pick(u, end, duration):
    """Best value for period ending `end`: lowest tag priority, then latest filing. Returns (val, filed) or (nan, NaT)."""
    s=u[u.end==end]
    if duration: s=s[_is_fy(s)]
    if s.empty: return np.nan,pd.NaT
    r=s.sort_values(["prio","filed"],ascending=[True,False]).iloc[0]
    return float(r.val),r.filed

def pit_snapshot(df, asof):
    """Latest fiscal year (from 10-K filings with filed<=asof). Flows and balance sheet come from the SAME fiscal year-end."""
    k=df[(df.filed<=asof)&df.form.isin(["10-K","10-K/A"])]
    rev=_union(k,FLOW["rev"]); rev=rev[_is_fy(rev)] if len(rev) else rev
    if rev.empty: return None
    fye=rev.end.max()
    if (asof-fye).days>MAX_STALE_DAYS: return None
    out={"fye":fye}
    out["rev"],out["filed"]=_pick(rev,fye,True)
    prevs=rev[((fye-rev.end).dt.days).between(340,390)]
    out["rev_prev"]=_pick(prevs,prevs.end.max(),True)[0] if len(prevs) else np.nan
    f=lambda key:_pick(_union(k,FLOW[key]),fye,True)[0]
    i=lambda key:_pick(_union(k,INST[key]),fye,False)[0]
    out["ni"]=f("ni"); out["cfo"]=f("cfo"); out["capex"]=f("capex")
    out["fcf"]=out["cfo"]-out["capex"] if np.isfinite(out["cfo"]) and np.isfinite(out["capex"]) else np.nan   # never assume capex=0
    c_all=i("cash_all")
    cash,sti=i("cash"),i("sti")
    # Do not treat absent cash components as zero. If cash is reported but short-term
    # investments are absent, use cash alone (conservative, documented proxy).
    out["cash"]=c_all if np.isfinite(c_all) else (cash+(sti if np.isfinite(sti) else 0.0) if np.isfinite(cash) else np.nan)
    dt=i("debt_total")
    if np.isfinite(dt): out["debt"]=dt                       # LongTermDebt already includes current maturities: do not add DebtCurrent
    else:
        nc,cu=i("debt_nc"),i("debt_c")
        # A missing debt tag is NOT evidence that a company has zero debt.
        out["debt"]=(nc if np.isfinite(nc) else 0.0)+(cu if np.isfinite(cu) else 0.0) if (np.isfinite(nc) and np.isfinite(cu)) else np.nan
    out["debt_found"]=bool(np.isfinite(dt) or np.isfinite(i("debt_nc")) or np.isfinite(i("debt_c")))
    out["eq"]=i("eq")
    sh=_union(k,SHARES)
    out["shares_asreported"],out["shares_filed"]=_pick(sh,fye,True)   # split factor must reference THIS value's own filing date
    if not np.isfinite(out["shares_asreported"]): return None
    return out

def split_factor_after(splits, date):
    """Product of split ratios (new/old) with ex-date strictly after `date`."""
    if splits is None or len(splits)==0: return 1.0
    return float(splits[splits.index>date].prod())

def dcf_gap(fcf, cash, debt, shares_adj, price, g, r=0.10, tg=0.03, n=5):
    """Per-share DCF gap (%). shares_adj must be on the SAME split basis as price."""
    if not (np.isfinite(fcf) and fcf>0 and np.isfinite(cash) and np.isfinite(debt) and np.isfinite(shares_adj) and shares_adj>0 and np.isfinite(price) and price>0): return np.nan
    pv=sum(fcf*(1+g)**t/(1+r)**t for t in range(1,n+1))
    tv=fcf*(1+g)**n*(1+tg)/(r-tg)/(1+r)**n
    eq=pv+tv+cash-debt
    return (eq/shares_adj/price-1)*100

def health_raw(s):
    rev,ni,fcf,cash,debt,eq,rp=[s.get(k,np.nan) for k in ("rev","ni","fcf","cash","debt","eq","rev_prev")]
    return dict(roe=ni/eq if np.isfinite(eq) and eq>0 else np.nan, margin=ni/rev if rev else np.nan, fcf_margin=fcf/rev if rev else np.nan,
                cash_debt=min(cash/debt,10) if np.isfinite(debt) and debt>0 and np.isfinite(cash) else (10.0 if np.isfinite(debt) and debt==0 and np.isfinite(cash) else np.nan),
                de=-(debt/eq) if np.isfinite(debt) and np.isfinite(eq) and eq>0 else np.nan, growth=rev/rp-1 if np.isfinite(rp) and rp>0 else np.nan)

def xs_pct(df):
    return df.rank(pct=True)*100

def build_scores(raw_health, dcf_gaps, sent):
    H=xs_pct(raw_health).mean(axis=1,skipna=True)
    V=(100+dcf_gaps).clip(0,100); Vr=xs_pct(dcf_gaps.to_frame()).iloc[:,0]
    S=(sent+100)/2; Sr=xs_pct(sent.to_frame()).iloc[:,0]
    return pd.DataFrame({"H":H,"V":V,"Vr":Vr,"S":S,"Sr":Sr})
