"""Real-data driver with caching/checkpoints at every slow stage. Normally started by launcher.py (RUN_ME.bat)."""
import argparse, os, sys, json, time, requests, numpy as np, pandas as pd
from pit import facts_to_df
from pipeline import build_panels, analyze
from sentiment import relevant, score_unique, sentiment_asof

def log(*a): print(time.strftime("%H:%M:%S"),*a,flush=True)

def sec_facts(tickers, ua, cache):
    os.makedirs(cache,exist_ok=True); H={"User-Agent":ua,"Accept-Encoding":"gzip, deflate"}
    m=requests.get("https://www.sec.gov/files/company_tickers.json",headers=H,timeout=60).json(); cik={v["ticker"].upper():int(v["cik_str"]) for v in m.values()}
    out={}
    for t in tickers:
        fn=f"{cache}/{t}.json"
        if not os.path.exists(fn):
            if t not in cik: log("  no SEC CIK for",t,"- dropped"); continue
            for k in range(4):
                r=requests.get(f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik[t]:010d}.json",headers=H,timeout=120)
                if r.status_code==200: break
                time.sleep(2*(k+1))
            if r.status_code!=200: log("  SEC download failed",t,r.status_code,"- dropped"); continue
            with open(fn,"w",encoding="utf-8") as f: f.write(r.text)
            time.sleep(0.2)
        with open(fn,encoding="utf-8") as f: out[t]=facts_to_df(json.load(f))
        log("  SEC ok",t,len(out[t]),"rows")
    return out

def prices(tickers,start,end,cache):
    import yfinance as yf
    os.makedirs(cache,exist_ok=True); C={};A={};S={}
    for t in tickers+["SPY"]:
        fn=f"{cache}/{t}.pkl"
        if os.path.exists(fn): h=pd.read_pickle(fn)
        else:
            h=None
            for k in range(4):
                try:
                    h=yf.Ticker(t).history(start=start,end=end,auto_adjust=False,actions=True)
                    if len(h): break
                except Exception as e: log("  yfinance retry",t,str(e)[:80])
                time.sleep(2*(k+1))
            if h is None or len(h)==0: log("  NO PRICES for",t,"- dropped"); continue
            h.index=pd.DatetimeIndex(h.index).tz_localize(None).normalize(); h.to_pickle(fn); time.sleep(0.5)
        C[t]=h["Close"]; A[t]=h["Adj Close"]
        s=h["Stock Splits"] if "Stock Splits" in h else pd.Series(dtype=float); S[t]=s[s>0]
    return pd.DataFrame(C),pd.DataFrame(A),S

def _col(cols,names):
    low={c.lower():c for c in cols}
    for n in names:
        if n in low: return low[n]
    return None

def _jsonl_chunks(path, columns, chunk_size=100_000):
    """Read JSONL record-by-record; report malformed records without aborting entire scan."""
    rows=[]; bad=0; total=0; examples=[]
    with open(path, "r", encoding="utf-8-sig", errors="replace") as stream:
        for line_no, line in enumerate(stream, 1):
            if not line.strip():
                continue
            total+=1
            try:
                record=json.loads(line)
                if not isinstance(record, dict):
                    raise ValueError("expected JSON object")
            except (ValueError, TypeError) as exc:
                bad+=1
                if len(examples)<5: examples.append(f"line {line_no}: {str(exc)[:100]}")
                continue
            rows.append({col:record.get(col) for col in columns})
            if len(rows)>=chunk_size:
                yield pd.DataFrame.from_records(rows, columns=columns)
                rows=[]
    if rows:
        yield pd.DataFrame.from_records(rows, columns=columns)
    log(f"  JSONL audit: {total:,} nonblank records, {bad:,} malformed records skipped")
    if examples: log("  JSONL errors: " + " | ".join(examples))
    if total and bad/total>0.01:
        raise RuntimeError(f"JSONL malformed record rate {bad/total:.2%} exceeds 1% safety threshold; do not trust this dataset")

def prepare_news(csv,tickers,start,end,cap,cache,chunk=300_000):
    """Stream the (multi-GB) FNSPID csv in chunks: keep sample tickers/window/relevant headlines, cap per ticker-month (deterministic hash)."""
    os.makedirs(cache,exist_ok=True); fn=f"{cache}/news_filtered.parquet"
    if os.path.exists(fn): log("news filter: using cache"); return pd.read_parquet(fn)
    isj=str(csv).lower().endswith((".jsonl",".json"))
    hdr=pd.read_json(csv,lines=True,nrows=1).columns if isj else pd.read_csv(csv,nrows=0,encoding="utf-8",encoding_errors="replace").columns
    cd,ct,cs=_col(hdr,["date","timestamp","published","datetime"]),_col(hdr,["article_title","title","headline"]),_col(hdr,["stock_symbol","ticker","symbol"])
    if not (cd and ct and cs): raise SystemExit(f"Cannot find date/title/ticker columns in {csv}. Columns found: {list(hdr)}")
    log(f"news columns -> date={cd}, title={ct}, ticker={cs}")
    lo,hi=pd.Timestamp(start)-pd.Timedelta(days=45),pd.Timestamp(end)+pd.Timedelta(days=1); keep=[];seen=0;t0=time.time(); tk=set(tickers)
    it=_jsonl_chunks(csv,[cd,ct,cs],min(chunk,100_000)) if isj else         pd.read_csv(csv,usecols=[cd,ct,cs],chunksize=chunk,encoding="utf-8",encoding_errors="replace",dtype=str,on_bad_lines="skip")
    for i,df in enumerate(it):
        df=df[[cd,ct,cs]].astype(str) if isj else df[[cd,ct,cs]]
        seen+=len(df); df.columns=["ts","headline","ticker"]; df["ticker"]=df.ticker.str.upper().str.strip()
        df=df[df.ticker.isin(tk)].dropna(subset=["headline","ts"])
        df["ts"]=pd.to_datetime(df.ts,utc=True,errors="coerce").dt.tz_localize(None); df=df.dropna(subset=["ts"]); df=df[(df.ts>=lo)&(df.ts<=hi)]
        df=df[df.headline.map(relevant)]; keep.append(df)
        if i%10==0: log(f"  news scan: {seen:,} rows read, {sum(map(len,keep)):,} kept ({(time.time()-t0)/60:.1f} min)")
    d=pd.concat(keep,ignore_index=True).drop_duplicates(["ticker","ts","headline"])
    if len(d)==0: raise SystemExit("No news rows matched the universe/date window. Check the CSV and the ticker list.")
    d["ym"]=d.ts.dt.to_period("M"); d["h"]=pd.util.hash_pandas_object(d.ticker+d.headline+d.ts.astype(str),index=False)
    d=d.sort_values("h").groupby(["ticker","ym"]).head(cap).drop(columns=["ym","h"]).reset_index(drop=True)
    d.to_parquet(fn); log(f"news kept after cap={cap}: {len(d):,} rows, {d.headline.nunique():,} unique headlines"); return d

def score_news(d,cache):
    u=sorted(d.headline.unique()); pc=score_unique(u,f"{cache}/finbert_parts",log=log)
    out=d[["ticker","ts"]].copy(); out["pc"]=d.headline.map(pc).values
    if out.pc.isna().any(): raise RuntimeError("Unscored headlines remain")
    return out

if __name__=="__main__":
    ap=argparse.ArgumentParser(); ap.add_argument("--universe",required=True); ap.add_argument("--news",default=None)
    ap.add_argument("--start",default="2015-01-31"); ap.add_argument("--end",default="2023-12-31"); ap.add_argument("--out",default="outputs"); ap.add_argument("--cache",default="cache")
    ap.add_argument("--cost_bps",type=float,default=10); ap.add_argument("--window",type=int,default=30); ap.add_argument("--cap",type=int,default=40); ap.add_argument("--ua",required=True); ap.add_argument("--no_news",action="store_true")
    a=ap.parse_args(); os.makedirs(a.out,exist_ok=True)
    tk=[l.strip().upper() for l in open(a.universe,encoding="utf-8") if l.strip()]
    log("1/5 SEC filings"); fx=sec_facts(tk,a.ua,f"{a.cache}/sec"); tk=[t for t in tk if t in fx]
    log("2/5 prices"); s0=(pd.Timestamp(a.start)-pd.DateOffset(months=14)).strftime("%Y-%m-%d"); e1=(pd.Timestamp(a.end)+pd.DateOffset(months=2)).strftime("%Y-%m-%d")
    close,adj,spl=prices(tk,s0,e1,f"{a.cache}/prices"); tk=[t for t in tk if t in close.columns]; log(f"universe after data checks: {len(tk)} tickers")
    if a.no_news:
        log("3-4/5 LIGHT MODE: news and FinBERT skipped (health + DCF only)"); news=None
    else:
        log("3/5 news filter"); nf=prepare_news(a.news,tk,a.start,a.end,a.cap,a.cache)
        log("4/5 FinBERT (resumable)"); news=score_news(nf,a.cache)
    log("5/5 panels + analysis"); P=build_panels(tk,close[tk],adj[tk],spl,fx,news,a.start,a.end,a.window); T=analyze(P,a.out,a.cost_bps)
    adj["SPY"].resample("ME").last().pct_change().dropna().to_csv(f"{a.out}/spy_monthly.csv")
    json.dump(dict({k:v for k,v in vars(a).items() if k!="ua"},tickers=tk,n_news=0 if news is None else int(len(news))),open(f"{a.out}/run_config.json","w"),indent=1,default=str)
    print(T.round(3).to_string()); log("DONE")
