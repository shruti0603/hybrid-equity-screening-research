# Hybrid equity screening research

Companion code and archived empirical outputs for *Combining Financial Health, DCF Valuation and FinBERT News Sentiment for Equity Selection: Point-in-Time Evidence and the News-Coverage Bottleneck*.

## Contents
- `pit.py`, `pipeline.py`, `backtest.py`, `sentiment.py`: research pipeline, preserved from the verified run.
- `run_split_correction.py`, `split_fix.py`: final valuation price-basis correction and analysis entry point. Earlier runners are included for input preparation only; their uncorrected valuation outputs must not be used as final results.
- `outputs/`: corrected tables and diagnostics, including valid subperiod results.
- `correction/`: archived correction evidence; control results are historical diagnostics, not final estimates.
- `verify_results.py`: checks selected reported statistics from archived outputs without raw data.

## Verify archived results
Use Python 3 in an isolated environment. Install `python -m pip install -r requirements.txt`, then run `python verify_results.py` and `python test_split_consistency.py`. These checks do not reproduce every empirical result from raw inputs.

## Full empirical rerun
The final offline runner is `python run_split_correction.py` from the repository root. It requires the original `cache/sec/*.json`, `cache/prices/*.pkl`, `lowdisk_final/selected_news.parquet` and `lowdisk_final/finbert_parts/manifest.json` plus matching scored parquet parts. These inputs are not distributed here. The runner checks input signatures and applies the split correction before final analysis. `run_all.py` and `final_lowdisk.py` are archived preparation scripts; obtaining matching historical inputs may require separate access to the original data sources. FinBERT scoring also requires PyTorch and the dependencies in `requirements_nlp.txt`. Exact historical input recovery is not guaranteed. Do not use the earlier uncorrected valuation results.

## Data and limitations
The study uses SEC filing-date accounting data, historical market data and a third-party copy of FNSPID news. Raw third-party data and cached headlines are excluded; access and redistribution are subject to source terms. Archived outputs cover 107 months for H+V and 19 months for H+S+V. The universe is survivorship-biased and news coverage is limited. The evidence does not establish incremental sentiment value. The archived invalid subperiod table is intentionally excluded; use `outputs/table_subperiods_valid.csv`.
