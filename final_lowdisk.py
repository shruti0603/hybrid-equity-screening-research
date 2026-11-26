"""IRFA low-disk, two-stage experiment. Source: sabareesh88/FNSPID_external, 13 Parquet shards.
No full dataset downloaded; only ticker/date/title columns streamed. Cache-only finance.
"""
import argparse, collections, datetime as dt, hashlib, json, os, pathlib, sqlite3, sys, zipfile
import pandas as pd
ROOT=pathlib.Path(__file__).resolve().parent
WORK=ROOT/'lowdisk_final'
REPO='sabareesh88/FNSPID_external'
SHARDS=13
MAX_ARTICLES=30  # per ticker/calendar month, deterministic earliest unique titles

def tickers():
    return set(x.strip().upper() for x in (ROOT/'universe_default.txt').read_text().splitlines() if x.strip())

def db():
    WORK.mkdir(exist_ok=True)
    con=sqlite3.connect(str(WORK/'articles.sqlite'))
    con.execute('PRAGMA journal_mode=DELETE')
    con.execute('CREATE TABLE IF NOT EXISTS news(ticker TEXT, ts TEXT, headline TEXT, PRIMARY KEY(ticker,ts,headline)) WITHOUT ROWID')
    con.execute('CREATE TABLE IF NOT EXISTS shards(shard INTEGER PRIMARY KEY, rows_seen INTEGER, matched INTEGER)')
    return con

def coverage(con):
    months=pd.period_range('2015-01','2023-12',freq='M')
    counts=collections.Counter()
    for t,ym,n in con.execute("SELECT ticker,substr(ts,1,7),count(*) FROM news GROUP BY ticker,substr(ts,1,7)"):
        counts[(t,ym)]=n
    rows=[]
    for m in months:
        d=m.strftime('%Y-%m')
        row={'month':d,'firms_1_article':sum(counts[(t,d)]>=1 for t in tickers()),'firms_3_articles':sum(counts[(t,d)]>=3 for t in tickers()),'articles':sum(counts[(t,d)] for t in tickers())}
        rows.append(row)
    pd.DataFrame(rows).to_csv(WORK/'coverage_pre_finbert.csv',index=False)
    eligible=sum(x['firms_3_articles']>=10 for x in rows)
    print(f'Coverage gate: {eligible}/108 months with >=10 firms and >=3 articles in calendar month (proxy, NOT final trading-date coverage)',flush=True)
    return eligible

def extract():
    from huggingface_hub import HfFileSystem
    import pyarrow.parquet as pq
    fs=HfFileSystem()
    con=db(); ts=tickers()
    for i in range(SHARDS):
        if con.execute('SELECT 1 FROM shards WHERE shard=?',(i,)).fetchone():
            print('Skipping completed shard',i,flush=True);continue
        path=f'datasets/{REPO}/data/train-{i:05d}-of-{SHARDS:05d}.parquet'
        print(f'Reading remote shard {i+1}/{SHARDS} (network transfer, no local Parquet copy)',flush=True)
        seen=matched=0
        with fs.open(path,'rb') as f:
            pf=pq.ParquetFile(f)
            cols=['Date','Article_title','Stock_symbol']
            missing=set(cols)-set(pf.schema.names)
            if missing:raise RuntimeError(f'Schema mismatch {missing} in {path}')
            for batch in pf.iter_batches(batch_size=4096,columns=cols):
                d=batch.to_pydict();seen+=len(d['Date']); insert=[]
                for rawdate,headline,ticker in zip(d['Date'],d['Article_title'],d['Stock_symbol']):
                    ticker=str(ticker or '').strip().upper()
                    if ticker not in ts or not headline:continue
                    date=pd.to_datetime(rawdate,utc=True,errors='coerce')
                    if pd.isna(date) or not ('2015-01-01'<=date.strftime('%Y-%m-%d')<='2023-12-31'):continue
                    insert.append((ticker,date.strftime('%Y-%m-%dT%H:%M:%S'),str(headline).strip()[:2000]))
                if insert:
                    con.executemany('INSERT OR IGNORE INTO news VALUES (?,?,?)',insert)
                    matched+=len(insert)
            con.execute('INSERT INTO shards VALUES (?,?,?)',(i,seen,matched));con.commit()
        print('Rows',seen,'candidate matches',matched,flush=True)
    eligible=coverage(con)
    (WORK/'source_manifest.json').write_text(json.dumps({'dataset':REPO,'shards':SHARDS,'source_revision':'main (unpinned; verify provenance)','max_articles_per_ticker_month':MAX_ARTICLES,'coverage_gate_months':eligible,'timestamp_note':'Date field treated as publication timestamp; verify semantics and timezone before claiming PIT','downloaded_full_dataset':False},indent=2))
    if eligible<24:
        print('STOP: fewer than 24 months pass preliminary coverage gate. No FinBERT run. Upload diagnostic ZIP.',flush=True)
        package();return
    # deterministically select earliest records per ticker/month, then keep all month-end eligibility tests separate
    selected=[];last=None;n=0
    for t,stamp,headline in con.execute('SELECT ticker,ts,headline FROM news ORDER BY ticker,substr(ts,1,7),ts,headline'):
        key=(t,stamp[:7]);n=n+1 if key==last else 1;last=key
        if n<=MAX_ARTICLES:selected.append((t,stamp,headline))
    pd.DataFrame(selected,columns=['ticker','ts','headline']).to_parquet(WORK/'selected_news.parquet',index=False)
    print('Selected',len(selected),'ticker-date-headline rows for FinBERT',flush=True)
    print('Next: RUN_FINAL_SCORE_AND_BACKTEST.bat',flush=True)

def score_and_backtest():
    from sentiment import score_unique
    from pit import facts_to_df
    from pipeline import build_panels,analyze
    import numpy as np
    source=WORK/'selected_news.parquet'
    if not source.exists():raise RuntimeError('No selected_news.parquet. Run coverage stage first; coverage gate may have failed.')
    nf=pd.read_parquet(source);nf['ts']=pd.to_datetime(nf.ts,utc=True).dt.tz_localize(None)
    u=sorted(nf.headline.dropna().unique())
    pc=score_unique(u,str(WORK/'finbert_parts'),part_size=5000,log=lambda s:print(s,flush=True))
    news=nf[['ticker','ts']].copy();news['pc']=nf.headline.map(pc)
    if news.pc.isna().any():raise RuntimeError('Missing FinBERT scores')
    cache=ROOT/'cache'; facts={};C={};A={};spl={}
    for t in sorted(tickers()):
        sf=cache/'sec'/f'{t}.json';pf=cache/'prices'/f'{t}.pkl'
        if not (sf.is_file() and pf.is_file()):continue
        facts[t]=facts_to_df(json.loads(sf.read_text(encoding='utf-8')))
        h=pd.read_pickle(pf);C[t]=h['Close'];A[t]=h['Adj Close'];spl[t]=h['Stock Splits'][h['Stock Splits']>0] if 'Stock Splits' in h else pd.Series(dtype=float)
    if len(facts)<10:raise RuntimeError('Insufficient local SEC/price caches; no downloads attempted')
    tk=list(facts)
    P=build_panels(tk,pd.DataFrame(C),pd.DataFrame(A),spl,facts,news,'2015-01-31','2023-12-31')
    out=WORK/'outputs';out.mkdir(exist_ok=True)
    T=analyze(P,str(out),cost_bps=10)
    print(T.to_string(index=False),flush=True)
    common=(P['H'].notna() & P['S'].notna() & P['V'].notna() & P['fwd'].notna()).sum(axis=1)
    months=int((common>=10).sum()); print('ACTUAL eligible full hybrid months:',months,flush=True)
    if months<24:print('STOP: insufficient full-hybrid history for main claim; results are exploratory only.',flush=True)
    (WORK/'experiment_manifest.json').write_text(json.dumps({'full_hybrid_months_ge10':months,'finbert_unique_headlines':len(u),'news_selection_cap_per_ticker_month':MAX_ARTICLES,'survivorship_bias':'50 currently selected firms','source':REPO,'methodology_warning':'Dataset coverage, timestamp semantics, valuation and survivor selection require journal-level validation'},indent=2))
    package()

def package():
    p=ROOT/'UPLOAD_ME_final_lowdisk.zip'
    with zipfile.ZipFile(p,'w',zipfile.ZIP_DEFLATED) as z:
        for path in WORK.rglob('*'):
            if path.is_file() and (path.suffix in ('.csv','.json','.md','.txt') or (path.parent.name=='outputs' and path.suffix=='.csv')):
                z.write(path,path.relative_to(ROOT))
    print('UPLOAD:',p,flush=True)

if __name__=='__main__':
    a=argparse.ArgumentParser();a.add_argument('stage',choices=['coverage','score']);v=a.parse_args()
    try:extract() if v.stage=='coverage' else score_and_backtest()
    except Exception as e:
        print('FAILED:',type(e).__name__,str(e),file=sys.stderr,flush=True)
        raise
