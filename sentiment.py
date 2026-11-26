"""FinBERT scoring with CHECKPOINTING + timestamped aggregation."""
import os, json, time, hashlib, numpy as np, pandas as pd

KEEP=("earnings","revenue","profit","stock","shares","investor","valuation","lawsuit","litigation","investigation","regulat","downgrade","upgrade","market","guidance")
BLOCK=("coupon","discount code","package release","tutorial")
def relevant(t):
    t=str(t).lower(); return any(k in t for k in KEEP) and not any(b in t for b in BLOCK)

_MODEL={}
def finbert_scorer(texts, batch=64, model="ProsusAI/finbert"):
    """texts -> DataFrame(label, conf). Loads the model once; fp16 on CUDA."""
    import torch
    from transformers import AutoTokenizer, AutoModelForSequenceClassification
    if "m" not in _MODEL:
        dev="cuda" if torch.cuda.is_available() else "cpu"
        tok=AutoTokenizer.from_pretrained(model); m=AutoModelForSequenceClassification.from_pretrained(model).eval().to(dev)
        if dev=="cuda": m=m.half()
        _MODEL.update(m=m,tok=tok,dev=dev,id2={int(k):v.lower() for k,v in m.config.id2label.items()})
    m,tok,dev,id2=_MODEL["m"],_MODEL["tok"],_MODEL["dev"],_MODEL["id2"]
    texts=list(texts); order=np.argsort([len(t) for t in texts]); out=[None]*len(texts)   # length-sorted batches are much faster
    for i in range(0,len(texts),batch):
        ix=order[i:i+batch]
        enc=tok([texts[j] for j in ix],padding=True,truncation=True,max_length=128,return_tensors="pt").to(dev)
        with torch.no_grad(): p=torch.softmax(m(**enc).logits.float(),-1).cpu().numpy()
        for j,row in zip(ix,p): k=int(row.argmax()); out[j]=(id2[k],float(row[k]))
    return pd.DataFrame(out,columns=["label","conf"])

def polarity_conf(df):
    return df.label.map({"positive":1,"negative":-1,"neutral":0})*df.conf

def score_unique(headlines, part_dir, scorer=finbert_scorer, part_size=5000, log=print):
    """Score a list of UNIQUE headlines in parts of `part_size`. Each finished part is saved atomically; re-running resumes
    after the last finished part. Returns Series headline -> polarity*confidence."""
    os.makedirs(part_dir,exist_ok=True); hs=list(headlines); n=len(hs)
    sig=hashlib.md5("\n".join(hs).encode("utf-8")).hexdigest(); mf=os.path.join(part_dir,"manifest.json")
    if os.path.exists(mf):
        old=json.load(open(mf,encoding="utf-8"))
        if old.get("sig")!=sig or old.get("part_size")!=part_size:
            raise RuntimeError(f"Checkpoint folder {part_dir} was made for different input (news filter/date/cap changed). Delete that folder to rescore.")
    else: json.dump({"sig":sig,"n":n,"part_size":part_size},open(mf,"w",encoding="utf-8"))
    nparts=(n+part_size-1)//part_size; done=sum(os.path.exists(os.path.join(part_dir,f"part_{p:05d}.parquet")) for p in range(nparts))
    log(f"FinBERT: {n:,} unique headlines, {nparts} parts, {done} already finished (resuming)." if done else f"FinBERT: {n:,} unique headlines in {nparts} parts.")
    t0=time.time(); new=0
    for p in range(nparts):
        fn=os.path.join(part_dir,f"part_{p:05d}.parquet")
        if os.path.exists(fn): continue
        chunk=hs[p*part_size:(p+1)*part_size]; r=scorer(chunk); r["pc"]=polarity_conf(r).values
        tmp=fn+".tmp"; pd.DataFrame({"headline":chunk,"pc":r.pc.values}).to_parquet(tmp); os.replace(tmp,fn)   # atomic: a crash never leaves a half part
        new+=len(chunk); el=max(time.time()-t0, 1e-6); left=n-(done*part_size)-new
        rate=new/el
        log(f"  part {p+1}/{nparts} saved | {rate:,.0f} headlines/s | ETA {max(left,0)/max(rate,1e-9)/60:,.0f} min")
    d=pd.concat([pd.read_parquet(os.path.join(part_dir,f"part_{p:05d}.parquet")) for p in range(nparts)],ignore_index=True)
    return d.set_index("headline").pc

def sentiment_asof(news, asof, window_days=30, min_n=3):
    """news: ticker, ts (UTC naive), pc. Uses ONLY ts<=asof (asof is 00:00 of the rebalance date => rebalance-day news excluded)."""
    w=news[(news.ts<=asof)&(news.ts>asof-pd.Timedelta(days=window_days))]
    g=w.groupby("ticker").pc.agg(["mean","count"]); s=100*g["mean"]; s[g["count"]<min_n]=np.nan; return s
