"""Split-basis correction helpers. The cached Close is retroactively split-adjusted (vendor convention); the final build_panels() multiplies shares only by splits up to
the trading date, which is correct only for AS-TRADED prices. to_as_traded() restores as-traded prices: Close(t) x product of split ratios with ex-date AFTER t."""
import numpy as np, pandas as pd
def _naive(idx):
    idx=pd.DatetimeIndex(idx); return idx.tz_localize(None) if idx.tz is not None else idx
def clean_splits(s):
    if s is None or len(s)==0: return pd.Series(dtype=float,index=pd.DatetimeIndex([]))
    s=pd.Series(s); s.index=_naive(s.index); return s[(s>0)&(s!=1)].sort_index()
def to_as_traded(close, splits):
    """close: DataFrame (dates x tickers) of split-adjusted Close; splits: dict ticker -> Series(ex-date -> ratio new/old shares)."""
    out=close.copy(); idx=_naive(out.index)
    for t in out.columns:
        for d,r in clean_splits(splits.get(t)).items():
            m=np.asarray(idx<d); out.loc[m,t]=out.loc[m,t]*float(r)
    return out
def jump_table(series_by_ticker, splits, tol=0.25):
    """For every split event with ratio far from 1 (|ln r|>tol, i.e. discriminating), return close_before/close_after and whether it looks as-traded (~ratio) or adjusted (~1)."""
    rows=[]
    for t,c in series_by_ticker.items():
        c=c.dropna()
        for d,r in clean_splits(splits.get(t)).items():
            if abs(np.log(r))<=tol: continue
            b=c[c.index<d]; a=c[c.index>=d]
            if len(b)==0 or len(a)==0: continue
            j=float(b.iloc[-1]/a.iloc[0]); rows.append(dict(ticker=t,ex_date=d.date(),ratio=float(r),jump=round(j,3),looks="as-traded" if abs(np.log(j/float(r)))<tol else ("adjusted" if abs(np.log(j))<tol else "ambiguous")))
    return pd.DataFrame(rows)
