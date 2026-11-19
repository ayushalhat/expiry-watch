"""RQ8 v2 additions (after comparing with an independent analysis of the same data):
 A. pre-trend table (half-years before the reform) and pre-only trend test
 B. last-bar share of daily variance (the RQ1 'last15_var_share' metric): expiry minus matched days, ITS and naive
 C. tail-sensitive per-bar ratios (ratio of means, bootstrap CI) alongside the median ratios
 D. whole-day absolute close-to-close return, expiry vs matched days: ITS
 E. Holm adjustment of the primary-family p-values
"""
import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np, pandas as pd
import statsmodels.api as sm
from scipy import stats
import rq8lib as R
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'out')
rng = np.random.default_rng(88)
s = R.base_sessions()
E = pd.read_pickle(f'{OUT}/Epre.pkl')        # ITS sample (367), primary rule
m = R.match(s, **R.SPECS['primary: vol20+vol5'])
rows = []
for e, cs in m.items():
    if e not in E.index: continue
    c = s.loc[cs]; x = s.loc[e]
    r = dict(date=e, VS_e=x.last_var_share, VS_c=c.last_var_share.mean(), A_e=abs(x.cc), A_c=c.cc.abs().mean())
    for i in range(1, 5): r[f'a{i}_e'] = x[f'abs{i}']; r[f'a{i}_c'] = c[f'abs{i}'].mean()
    rows.append(r)
X = pd.DataFrame(rows).set_index('date').sort_index().join(E[['t', 'period', 'type', 'lL', 'lE', 'EVR', 'L15R']], how='inner')
X['dVS'] = 100 * (X.VS_e - X.VS_c)           # percentage points
X['lA'] = np.log((X.A_e + .5) / (X.A_c + .5))
X['post'] = (X.index >= R.D1).astype(float); X['tue'] = (X.index >= R.D2).astype(float)
res = {'n': len(X)}

def its(y, maxlags=4):
    Z = pd.DataFrame({'c': 1.0, 't': X.t, 'D1': X.post, 'D2': X.tue}, index=X.index)
    f = sm.OLS(X[y], Z).fit(cov_type='HAC', cov_kwds={'maxlags': maxlags}); return f

# ---- A: pre-trend ----
pre = X[X.index < R.D1]
Z = pd.DataFrame({'c': 1.0, 't': pre.t}, index=pre.index)
rowsA = []
for y, nm in [('lL', 'log L15R'), ('lE', 'log EVR'), ('dVS', 'last-bar variance share gap (pp)')]:
    f = sm.OLS(pre[y], Z).fit(cov_type='HAC', cov_kwds={'maxlags': 4})
    rowsA.append(dict(outcome=nm, slope_per_year=f.params['t'], se=f.bse['t'], p=f.pvalues['t'], lo=f.params['t'] - 1.96 * f.bse['t'], hi=f.params['t'] + 1.96 * f.bse['t'], n=len(pre)))
PT = pd.DataFrame(rowsA); PT.to_csv(f'{OUT}/v2_pretrend_slopes.csv', index=False); print(PT.round(3).to_string())
h = np.where(X.index.month <= 6, 'H1', 'H2'); X['half'] = X.index.year.astype(str) + h
HT = X[(X.index >= '2022-07-01') & (X.index < R.D1)].groupby('half').agg(n=('L15R', 'size'), L15R_med=('L15R', 'median'), EVR_med=('EVR', 'median'), VSgap_pp=('dVS', 'mean'))
HT.to_csv(f'{OUT}/v2_pretrend_halves.csv'); print(HT.round(2).to_string())

# ---- B: variance share ----
rowsB = []
for lab, a, b in [('Weekly', X[X.type == 'weekly'], None), ('Monthly', X[X.type == 'monthly'], None), ('All pre-CAS expiries', X, None)]:
    rowsB.append(dict(group=lab, n=len(a), VS_expiry_mean=100 * a.VS_e.mean(), VS_ctrl_mean=100 * a.VS_c.mean(), gap_pp=a.dVS.mean(), med_gap_pp=a.dVS.median()))
VSsum = pd.DataFrame(rowsB); VSsum.to_csv(f'{OUT}/v2_vs_summary.csv', index=False); print(VSsum.round(2).to_string())
rowsB = []
f = its('dVS')
for term in ['t', 'D1', 'D2']:
    rowsB.append(dict(outcome='last-bar variance share, expiry minus matched (pp)', term=term, coef=f.params[term], se=f.bse[term], p=f.pvalues[term], lo=f.params[term] - 1.96 * f.bse[term], hi=f.params[term] + 1.96 * f.bse[term]))
pa, pb = X[X.period == 'P0'].dVS, X[X.period.isin(['P1', 'P2', 'P3'])].dVS
res['vs_naive'] = dict(pre_mean=float(pa.mean()), post_mean=float(pb.mean()), mw_p=float(stats.mannwhitneyu(pa, pb).pvalue), pre_med=float(pa.median()), post_med=float(pb.median()))
VSits = pd.DataFrame(rowsB); VSits.to_csv(f'{OUT}/v2_vs_its.csv', index=False); print(VSits.round(3).to_string()); print(res['vs_naive'])

# ---- C: tail-sensitive per-bar ratios ----
def ratio_of_means(g, i): return g[f'a{i}_e'].mean() / g[f'a{i}_c'].mean()
rowsC = []
P0 = X[X.period == 'P0']; PP = X[X.period.isin(['P1', 'P2', 'P3'])]
for i, lab in enumerate(['09:15-11:15', '11:15-13:15', '13:15-15:15', '15:15-15:30'], start=1):
    r = dict(bar=lab)
    for nm, g in [('pre', P0), ('post', PP)]:
        est = ratio_of_means(g, i); bs = [ratio_of_means(g.iloc[rng.integers(0, len(g), len(g))], i) for _ in range(3000)]
        r[nm] = est; r[nm + '_lo'] = np.percentile(bs, 2.5); r[nm + '_hi'] = np.percentile(bs, 97.5)
    # difference: bootstrap
    d = [ratio_of_means(PP.iloc[rng.integers(0, len(PP), len(PP))], i) - ratio_of_means(P0.iloc[rng.integers(0, len(P0), len(P0))], i) for _ in range(3000)]
    r['diff'] = r['post'] - r['pre']; r['diff_lo'] = np.percentile(d, 2.5); r['diff_hi'] = np.percentile(d, 97.5)
    rowsC.append(r)
C = pd.DataFrame(rowsC); C.to_csv(f'{OUT}/v2_bar_means.csv', index=False); print(C.round(2).to_string())

# ---- D: whole-day absolute return ----
rowsD = []
f = its('lA')
for term in ['t', 'D1', 'D2']:
    rowsD.append(dict(outcome='log(|close-to-close|) expiry / matched', term=term, coef=f.params[term], se=f.bse[term], p=f.pvalues[term], lo=f.params[term] - 1.96 * f.bse[term], hi=f.params[term] + 1.96 * f.bse[term]))
D = pd.DataFrame(rowsD); D.to_csv(f'{OUT}/v2_absret_its.csv', index=False); print(D.round(3).to_string())
res['absret_medians'] = {p: float(X[X.period == p].lA.median()) for p in ['P0', 'P1', 'P2', 'P3']}
# ---- E: Holm ----
I = pd.read_csv(f'{OUT}/its.csv'); I = I[(I['sample'] == 'all expiries') & (I.spec == 'levels') & I.term.isin(['D1', 'D2'])]
fam = I[I.outcome.isin(['log L15R', 'log EVR', 'alert L15R>3 (LPM)'])]
def holm(p):
    p = np.asarray(p); o = np.argsort(p); mm = len(p); adj = np.empty(mm); run = 0
    for rk, i in enumerate(o): run = max(run, (mm - rk) * p[i]); adj[i] = min(1, run)
    return adj
fam = fam.assign(p_holm=holm(fam.p.values)); fam[['outcome', 'term', 'coef', 'p', 'p_holm']].to_csv(f'{OUT}/v2_holm_primary.csv', index=False); print(fam[['outcome', 'term', 'coef', 'p', 'p_holm']].round(3).to_string())
fam8 = I.assign(p_holm=holm(I.p.values)); res['holm8_alertE_D1'] = float(fam8[(fam8.outcome.str.contains('EVR>2.7')) & (fam8.term == 'D1')].p_holm.iloc[0])
json.dump(res, open(f'{OUT}/v2.json', 'w'), indent=1, default=str); print(res)
