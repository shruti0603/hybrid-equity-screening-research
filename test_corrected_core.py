import unittest, numpy as np, pandas as pd
from pit import dcf_gap,health_raw,pit_snapshot
from backtest import top_n_returns
class Tests(unittest.TestCase):
 def test_missing_debt_not_zero(self):
  d=pd.DataFrame([dict(tag='Revenues',start=pd.Timestamp('2019-01-01'),end=pd.Timestamp('2019-12-31'),val=100.,filed=pd.Timestamp('2020-02-01'),form='10-K',fp='FY'),dict(tag='WeightedAverageNumberOfSharesOutstandingBasic',start=pd.Timestamp('2019-01-01'),end=pd.Timestamp('2019-12-31'),val=10.,filed=pd.Timestamp('2020-02-01'),form='10-K',fp='FY')]);s=pit_snapshot(d,pd.Timestamp('2020-03-01'));self.assertTrue(np.isnan(s['debt']))
 def test_dcf_requires_debt(self):self.assertTrue(np.isnan(dcf_gap(10,5,np.nan,10,10,.1)))
 def test_health_debt_missing(self):self.assertTrue(np.isnan(health_raw(dict(rev=100,ni=10,fcf=5,cash=20,debt=np.nan,eq=50,rev_prev=90))['cash_debt']))
 def test_turnover(self):
  ix=pd.date_range('2020-01-31',periods=2,freq='ME'); cols=[f'T{i}' for i in range(10)];scores=pd.DataFrame(0.,index=ix,columns=cols);scores.loc[ix[0],cols[:2]]=100;scores.loc[ix[1],cols[:2]]=100;returns=pd.DataFrame(.01,index=ix,columns=cols);g,n,t=top_n_returns(scores,returns);self.assertAlmostEqual(t.iloc[0],1.0);self.assertAlmostEqual(t.iloc[1],0.0)
if __name__=='__main__':unittest.main()
