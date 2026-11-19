"""Sign-conditional reversal tests (drift-free). Primary test of RQ5."""
import json, sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np, pandas as pd
import statsmodels.api as sm
from scipy import stats
import rq5lib as L
import rq5_panel as P

OUT = sys.argv[1]
d = pd.read_pickle(f'{OUT}/panel.pkl')
s = P.build_panel()
d['hit_gap'] = np.where(d.gap.isna(), np.nan, (np.sign(d.gap) == -d.sgn).astype(float))
d['hit_d1'] = np.where(d.d1.isna(), np.nan, (np.sign(d.d1) == -d.sgn).astype(float))
res = {}


def sign_matched(covs=('vol20', 'vol5', 'prev_abs'), k=12, min_ctrl=3, hit='hit_gap'):
    mc = L.match_controls(s, k=k, covs=covs)
    rows = []
    for e, cs in mc.items():
        if e not in d.index or pd.isna(d.loc[e, hit]): continue
        c = d.reindex(cs)
        c = c[(c.sgn == d.loc[e, 'sgn']) & c[hit].notna()]
        if len(c) < min_ctrl: continue
        rows.append(dict(date=e, typ=s.loc[e, 'exp_type'], qe=bool(s.loc[e, 'quarter_end']), sgn=d.loc[e, 'sgn'],
                         hit_e=d.loc[e, hit], hit_c=c[hit].mean(), nctrl=len(c)))
    return pd.DataFrame(rows).set_index('date')


def summarise(label, g):
    dd = g.hit_e - g.hit_c
    n = len(dd); m = dd.mean(); se = dd.std(ddof=1) / np.sqrt(n)
    return dict(group=label, n=n, rev_exp=100 * g.hit_e.mean(), rev_ctrl=100 * g.hit_c.mean(), diff_pp=100 * m, se_pp=100 * se,
                lo=100 * (m - 1.96 * se), hi=100 * (m + 1.96 * se), p=2 * (1 - stats.norm.cdf(abs(m / se))))

S = sign_matched()
S.to_csv(f'{OUT}/sign_matched_pairs.csv')
rows = [summarise('All expiries', S), summarise('Weekly only', S[S.typ == 'weekly']), summarise('Monthly', S[S.typ == 'monthly']),
        summarise('Quarter-end monthly', S[S.qe]),
        summarise('Late move up', S[S.sgn > 0]), summarise('Late move down', S[S.sgn < 0]),
        summarise('2019-22', S[S.index < '2023-01-01']), summarise('2023-26', S[S.index >= '2023-01-01']),
        summarise('Thursday expiries', S[S.index.weekday == 3]), summarise('Tuesday expiries', S[S.index.weekday == 1]),
        summarise('All, excl. 2020', S[S.index.year != 2020])]
T1 = pd.DataFrame(rows); T1.to_csv(f'{OUT}/primary_sign_matched.csv', index=False); print(T1.round(2).to_string())
res['primary'] = rows[0]; res['primary_n_dropped'] = int(367 - len(S))

# robustness of the primary test to the matching rule
rob = []
for nm, covs, k, mn in [('default covariates, 12 nearest (primary)', ('vol20', 'vol5', 'prev_abs'), 12, 3),
                        ('default covariates, 20 nearest', ('vol20', 'vol5', 'prev_abs'), 20, 3),
                        ('vol20 only, 12 nearest', ('vol20',), 12, 3),
                        ('5 covariates, 12 nearest', ('vol20', 'range5', 'ret5', 'prev_abs', 'firstbars_vol'), 12, 3),
                        ('default covariates, 8 nearest, min 2', ('vol20', 'vol5', 'prev_abs'), 8, 2)]:
    x = sign_matched(covs, k, mn)
    r = summarise(nm, x); rob.append(r)
ROB = pd.DataFrame(rob); ROB.to_csv(f'{OUT}/primary_robust_matching.csv', index=False); print(ROB.round(2).to_string())

# next-day close version
S1 = sign_matched(hit='hit_d1')
T1d = pd.DataFrame([summarise('All expiries (next close)', S1), summarise('Weekly (next close)', S1[S1.typ == 'weekly']), summarise('Monthly (next close)', S1[S1.typ == 'monthly'])])
T1d.to_csv(f'{OUT}/primary_nextclose.csv', index=False); print(T1d.round(2).to_string())

# drift-free linear-probability DiD on all sessions: P(gap>0) = a + b E + c up + e (E x up)
d['up'] = (d.sgn > 0).astype(int)
lpm = []
for hit, y in [('gap', 'gap'), ('d1', 'd1')]:
    dd = d[d[y].notna()].copy(); dd['pos'] = (dd[y] > 0).astype(float)
    for spec in ['pooled', 'split']:
        if spec == 'pooled':
            X = pd.DataFrame({'const': 1.0, 'E': dd.E, 'up': dd.up, 'E_up': dd.E * dd.up})
            terms = ['E_up']
        else:
            X = pd.DataFrame({'const': 1.0, 'Ew': dd.Ew, 'Em': dd.Em, 'up': dd.up, 'Ew_up': dd.Ew * dd.up, 'Em_up': dd.Em * dd.up})
            terms = ['Ew_up', 'Em_up']
        m = sm.OLS(dd.pos, X).fit(cov_type='HAC', cov_kwds={'maxlags': 5})
        for t in terms:
            lpm.append(dict(outcome=y, spec=spec, term=t, pp=100 * m.params[t], se_pp=100 * m.bse[t], p=m.pvalues[t], n=len(dd)))
    # baseline normal-day L-sign sensitivity
    X = pd.DataFrame({'const': 1.0, 'up': dd.up}); mm = sm.OLS(dd[dd.E == 0].pos, X[dd.E == 0]).fit()
    lpm.append(dict(outcome=y, spec='baseline non-expiry', term='up', pp=100 * mm.params['up'], se_pp=100 * mm.bse['up'], p=mm.pvalues['up'], n=int((dd.E == 0).sum())))
    ex = dd[dd.E == 1]
    lpm.append(dict(outcome=y, spec='expiry only', term='P(+|up)-P(+|down)', pp=100 * (ex[ex.up == 1].pos.mean() - ex[ex.up == 0].pos.mean()), se_pp=np.nan, p=np.nan, n=len(ex)))
LPM = pd.DataFrame(lpm); LPM.to_csv(f'{OUT}/lpm_did.csv', index=False); print(LPM.round(3).to_string())

# power: minimum detectable difference
se = T1.loc[0, 'se_pp']; res['mde_pp'] = float(2.8 * se)
# split-sample stability: bootstrap over expiries
rng = np.random.default_rng(11)
dd = (S.hit_e - S.hit_c).values
bs = [rng.choice(dd, len(dd)).mean() for _ in range(10000)]
res['boot_ci'] = [float(100 * np.percentile(bs, 2.5)), float(100 * np.percentile(bs, 97.5))]
# exact-ish: sign test on paired difference
res['share_expiries_less_reversal'] = float((dd < 0).mean())
json.dump(res, open(f'{OUT}/final.json', 'w'), indent=1, default=str)
print(json.dumps(res, indent=1, default=str))
