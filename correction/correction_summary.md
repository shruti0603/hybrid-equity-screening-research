# Split-basis correction: summary

Corrected run = cached Close converted to as-traded prices; pipeline code unchanged. All figures below are recomputed; the 'previous run' column exists only to test reproduction.

| metric                                                   |   previous_run_pre_correction |   control_rerun_as_before |   corrected | control_reproduces_previous   |   corrected_minus_previous |
|:---------------------------------------------------------|------------------------------:|--------------------------:|------------:|:------------------------------|---------------------------:|
| H+V (own sample): net CAGR                               |                       0.10237 |                   0.10237 |     0.11233 | True                          |                    0.00995 |
| H+V: net Sharpe                                          |                       0.56572 |                   0.56572 |     0.62105 | True                          |                    0.05532 |
| H+V: max drawdown                                        |                      -0.33492 |                  -0.33492 |    -0.33481 | True                          |                    0.00012 |
| H+V: mean IC                                             |                      -0.00295 |                  -0.00295 |    -0.02792 | True                          |                   -0.02497 |
| H+V: NW t(IC)                                            |                      -0.11466 |                  -0.11466 |    -1.1128  | True                          |                   -0.99814 |
| H+V: months                                              |                     107       |                 107       |   107       | True                          |                    0       |
| H+V: mean turnover                                       |                       0.13505 |                   0.13505 |     0.1148  | True                          |                   -0.02025 |
| H+V: gross CAGR                                          |                       0.10415 |                   0.10415 |     0.11385 | True                          |                    0.0097  |
| EW same firms: net CAGR                                  |                       0.15525 |                   0.15525 |     0.15525 | True                          |                    0       |
| EW same firms: Sharpe                                    |                       1.01055 |                   1.01055 |     1.01055 | True                          |                    0       |
| EW same firms: max drawdown                              |                      -0.22134 |                  -0.22134 |    -0.22134 | True                          |                   -0       |
| Sharpe diff H+V - EW                                     |                      -0.44307 |                  -0.44307 |    -0.38477 | True                          |                    0.05831 |
| Sharpe diff lo                                           |                      -0.79982 |                  -0.79982 |    -0.73099 | True                          |                    0.06884 |
| Sharpe diff hi                                           |                      -0.11276 |                  -0.11276 |    -0.06749 | True                          |                    0.04527 |
| [H,S,V sample] Full 50/30/20 (H,S,V): months             |                      19       |                  19       |    19       | True                          |                    0       |
| [H,S,V sample] Full 50/30/20 (H,S,V): net CAGR           |                       0.23486 |                   0.23486 |     0.24294 | True                          |                    0.00808 |
| [H,S,V sample] Full 50/30/20 (H,S,V): net Sharpe         |                       1.03849 |                   1.03849 |     1.05488 | True                          |                    0.01639 |
| [H,S,V sample] Full 50/30/20 (H,S,V): mean IC            |                      -0.01521 |                  -0.01521 |    -0.02524 | True                          |                   -0.01003 |
| [H,S,V sample] Full 50/30/20 (H,S,V): NW t(IC)           |                      -0.3482  |                  -0.3482  |    -0.49063 | True                          |                   -0.14243 |
| [H,S,V sample] Equal 1/3: months                         |                      19       |                  19       |    19       | True                          |                    0       |
| [H,S,V sample] Equal 1/3: net CAGR                       |                       0.31928 |                   0.31928 |     0.30245 | True                          |                   -0.01683 |
| [H,S,V sample] Equal 1/3: net Sharpe                     |                       1.5021  |                   1.5021  |     1.40805 | True                          |                   -0.09405 |
| [H,S,V sample] Equal 1/3: mean IC                        |                       0.02575 |                   0.02575 |    -0.00078 | True                          |                   -0.02653 |
| [H,S,V sample] Equal 1/3: NW t(IC)                       |                       0.58807 |                   0.58807 |    -0.01423 | True                          |                   -0.60231 |
| [H,S,V sample] H only: months                            |                      19       |                  19       |    19       | True                          |                    0       |
| [H,S,V sample] H only: net CAGR                          |                       0.27439 |                   0.27439 |     0.27439 | True                          |                    0       |
| [H,S,V sample] H only: net Sharpe                        |                       1.15476 |                   1.15476 |     1.15476 | True                          |                    0       |
| [H,S,V sample] H only: mean IC                           |                      -0.03105 |                  -0.03105 |    -0.03105 | True                          |                   -0       |
| [H,S,V sample] H only: NW t(IC)                          |                      -0.82932 |                  -0.82932 |    -0.82932 | True                          |                    0       |
| [H,S,V sample] S only: months                            |                      19       |                  19       |    19       | True                          |                    0       |
| [H,S,V sample] S only: net CAGR                          |                       0.16971 |                   0.16971 |     0.16971 | True                          |                    0       |
| [H,S,V sample] S only: net Sharpe                        |                       0.82393 |                   0.82393 |     0.82393 | True                          |                    0       |
| [H,S,V sample] S only: mean IC                           |                      -0.06877 |                  -0.06877 |    -0.06877 | True                          |                   -0       |
| [H,S,V sample] S only: NW t(IC)                          |                      -1.20795 |                  -1.20795 |    -1.20795 | True                          |                    0       |
| [H,S,V sample] V only: months                            |                      19       |                  19       |    19       | True                          |                    0       |
| [H,S,V sample] V only: net CAGR                          |                       0.24566 |                   0.24566 |     0.13864 | True                          |                   -0.10702 |
| [H,S,V sample] V only: net Sharpe                        |                       1.09325 |                   1.09325 |     0.71796 | True                          |                   -0.3753  |
| [H,S,V sample] V only: mean IC                           |                       0.07891 |                   0.07891 |     0.03508 | True                          |                   -0.04384 |
| [H,S,V sample] V only: NW t(IC)                          |                       1.27299 |                   1.27299 |     0.49718 | True                          |                   -0.77581 |
| [H,S,V sample] H+V: months                               |                      19       |                  19       |    19       | True                          |                    0       |
| [H,S,V sample] H+V: net CAGR                             |                       0.19136 |                   0.19136 |     0.19136 | True                          |                    0       |
| [H,S,V sample] H+V: net Sharpe                           |                       0.8642  |                   0.8642  |     0.8642  | True                          |                    0       |
| [H,S,V sample] H+V: mean IC                              |                       0.03294 |                   0.03294 |     0.00945 | True                          |                   -0.02349 |
| [H,S,V sample] H+V: NW t(IC)                             |                       0.68905 |                   0.68905 |     0.15982 | True                          |                   -0.52923 |
| [H,S,V sample] H+S: months                               |                      19       |                  19       |    19       | True                          |                    0       |
| [H,S,V sample] H+S: net CAGR                             |                       0.33273 |                   0.33273 |     0.33273 | True                          |                    0       |
| [H,S,V sample] H+S: net Sharpe                           |                       1.5641  |                   1.5641  |     1.5641  | True                          |                    0       |
| [H,S,V sample] H+S: mean IC                              |                      -0.01897 |                  -0.01897 |    -0.01897 | True                          |                   -0       |
| [H,S,V sample] H+S: NW t(IC)                             |                      -0.60374 |                  -0.60374 |    -0.60374 | True                          |                    0       |
| [H,S,V sample] S+V: months                               |                      19       |                  19       |    19       | True                          |                    0       |
| [H,S,V sample] S+V: net CAGR                             |                       0.17838 |                   0.17838 |     0.1208  | True                          |                   -0.05758 |
| [H,S,V sample] S+V: net Sharpe                           |                       0.88178 |                   0.88178 |     0.69985 | True                          |                   -0.18192 |
| [H,S,V sample] S+V: mean IC                              |                       0.01336 |                   0.01336 |    -0.02358 | True                          |                   -0.03693 |
| [H,S,V sample] S+V: NW t(IC)                             |                       0.28176 |                   0.28176 |    -0.42829 | True                          |                   -0.71004 |
| [H,S,V sample] Full, rank variants (H,Sr,Vr): months     |                      19       |                  19       |    19       | True                          |                    0       |
| [H,S,V sample] Full, rank variants (H,Sr,Vr): net CAGR   |                       0.12965 |                   0.12965 |     0.1237  | True                          |                   -0.00596 |
| [H,S,V sample] Full, rank variants (H,Sr,Vr): net Sharpe |                       0.69519 |                   0.69519 |     0.64628 | True                          |                   -0.04891 |
| [H,S,V sample] Full, rank variants (H,Sr,Vr): mean IC    |                      -0.03621 |                  -0.03621 |    -0.05755 | True                          |                   -0.02134 |
| [H,S,V sample] Full, rank variants (H,Sr,Vr): NW t(IC)   |                      -0.92533 |                  -0.92533 |    -1.23524 | True                          |                   -0.30991 |
| [H,S,V sample] V rank only: months                       |                      19       |                  19       |    19       | True                          |                    0       |
| [H,S,V sample] V rank only: net CAGR                     |                       0.34309 |                   0.34309 |     0.25366 | True                          |                   -0.08943 |
| [H,S,V sample] V rank only: net Sharpe                   |                       1.27462 |                   1.27462 |     1.24892 | True                          |                   -0.0257  |
| [H,S,V sample] V rank only: mean IC                      |                       0.08013 |                   0.08013 |     0.03124 | True                          |                   -0.04889 |
| [H,S,V sample] V rank only: NW t(IC)                     |                       1.45759 |                   1.45759 |     0.49082 | True                          |                   -0.96677 |
| [H,S,V sample] 12-1 momentum: months                     |                      19       |                  19       |    19       | True                          |                    0       |
| [H,S,V sample] 12-1 momentum: net CAGR                   |                       0.3131  |                   0.3131  |     0.3131  | True                          |                    0       |
| [H,S,V sample] 12-1 momentum: net Sharpe                 |                       1.05151 |                   1.05151 |     1.05151 | True                          |                    0       |
| [H,S,V sample] 12-1 momentum: mean IC                    |                      -0.00652 |                  -0.00652 |    -0.00652 | True                          |                   -0       |
| [H,S,V sample] 12-1 momentum: NW t(IC)                   |                      -0.1184  |                  -0.1184  |    -0.1184  | True                          |                   -0       |
| [H,S,V sample] EW eligible universe: months              |                      19       |                  19       |    19       | True                          |                    0       |
| [H,S,V sample] EW eligible universe: net CAGR            |                       0.26896 |                   0.26896 |     0.26896 | True                          |                    0       |
| [H,S,V sample] EW eligible universe: net Sharpe          |                       1.3886  |                   1.3886  |     1.3886  | True                          |                    0       |

## Effect on valuation

```
{
 "panels_identical_H_S_Sr_fwd_mom": {
  "H": true,
  "S": true,
  "Sr": true,
  "fwd": true,
  "mom": true
 },
 "V_availability_identical": true,
 "valuation_firm_months": 2273,
 "firm_months_changed": 365,
 "share_changed": 0.16058073031236253,
 "firms_changed": [
  "AAPL",
  "AMZN",
  "HON",
  "IBM",
  "MRK",
  "NKE",
  "PFE",
  "T",
  "TSLA",
  "WMT"
 ],
 "median_gap_changed_control": 162.24976386578555,
 "median_gap_changed_corrected": -17.132223911621935,
 "V_pinned_at_100_changed_control": 0.8027397260273973,
 "V_pinned_at_100_changed_corrected": 0.3863013698630137,
 "monthly_spearman_V_control_vs_corrected_median": 0.8425547495914718,
 "monthly_spearman_V_min": 0.30562665039721165,
 "months_positive_median_gap_control": 22,
 "months_positive_median_gap_corrected": 0
}
```
