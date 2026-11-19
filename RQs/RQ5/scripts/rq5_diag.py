import json, sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np, pandas as pd
import statsmodels.api as sm
from scipy import stats
import rq5lib as L

OUT = sys.argv[1]
d = pd.read_pickle(f'{OUT}/panel.pkl')
M = pd.read_csv(f'{OUT}/matched_pairs.csv', index_col=0, parse_dates=True)
rng = np.random.default_rng(7)
res = {}

# a) drift diagnostics
d = d.copy()
d['gap_pos'] = (d.gap > 0).astype(float)
res['pgap_pos_exp'] = float(d[d.E == 1].gap_pos.mean()); res['pgap_pos_non'] = float(d[d.E == 0].gap_pos.mean())
res['median_gap_exp'] = float(d[d.E == 1].gap.median()); res['median_gap_non'] = float(d[d.E == 0].gap.median())
th = d[d.index < '2025-09-01']
wd = th.groupby(th.index.weekday).agg(p_gap_pos=('gap_pos', 'mean'), med_gap=('gap', 'median'), n=('gap', 'size'))
print('Thursday-era P(gap>0) by weekday of session t (Mon=0):\n', wd.round(3))
res['pgap_by_weekday_thu_era'] = wd.round(3).to_dict()
# conditional on late-move sign
for nm, m in [('exp', d.E == 1), ('non', d.E == 0)]:
    g = d[m]
    res[f'pgap_pos_{nm}_given_up'] = float(g[g.late > 0].gap_pos.mean()); res[f'pgap_pos_{nm}_given_down'] = float(g[g.late < 0].gap_pos.mean())
print({k: round(v, 3) for k, v in res.items() if isinstance(v, float)})

# b) sign-balanced matched hit-rate difference: 0.5*(diff_up + diff_down), cancels a sign-independent overnight drift
def balanced(g):
    out = []
    for sgn in (1, -1):
        h = g[np.sign(g.L_e) == sgn]
        dd = (h.hit_e - h.hit_c).dropna()
        out.append((dd.mean(), dd.var(ddof=1) / len(dd), len(dd)))
    est = 0.5 * (out[0][0] + out[1][0]); se = 0.5 * np.sqrt(out[0][1] + out[1][1])
    return 100 * est, 100 * se, out[0][2], out[1][2]

rows = []
def add(label, g):
    est, se, nu, nd = balanced(g)
    rows.append(dict(group=label, n=len(g), n_up=nu, n_down=nd, diff_pp=est, se_pp=se, lo=est - 1.96 * se, hi=est + 1.96 * se,
                     p=2 * (1 - stats.norm.cdf(abs(est / se)))))
add('All expiries', M)
add('Weekly', M[M.typ == 'weekly']); add('Monthly', M[M.typ == 'monthly'])
add('Quarter-end monthly', M[M.qe])
add('2019-22', M[M.index < '2023-01-01']); add('2023-26', M[M.index >= '2023-01-01'])
add('Thursday expiries', M[M.index.weekday == 3]); add('Tuesday expiries', M[M.index.weekday == 1])
add('All, ex 2020', M[M.index.year != 2020])
HB = pd.DataFrame(rows); HB.to_csv(f'{OUT}/hit_balanced.csv', index=False); print(HB.round(3).to_string())

# c) tail tests with robustness to the COVID window and to the single largest observations
t = d[d.zL >= 2.0]
def tail_diff(t_, h='d1'):
    a = t_[t_.E == 1][f'Y_{h}'].dropna(); b = t_[t_.E == 0][f'Y_{h}'].dropna()
    diff = a.mean() - b.mean()
    bs = []
    av, bv = a.values, b.values
    for _ in range(5000):
        bs.append(rng.choice(av, len(av)).mean() - rng.choice(bv, len(bv)).mean())
    pv = np.concatenate([av, bv]); pm = []
    for _ in range(5000):
        rng.shuffle(pv); pm.append(pv[:len(av)].mean() - pv[len(av):].mean())
    return dict(diff=diff, lo=np.percentile(bs, 2.5), hi=np.percentile(bs, 97.5), p_perm=(np.abs(pm) >= abs(diff)).mean(), n_e=len(av), n_n=len(bv),
                med_e=a.median(), med_n=b.median())
tl = []
variants = {
    'z>=2, all': t,
    'z>=2, ex-COVID (15Feb-30Jun 2020)': t[~((t.index >= '2020-02-15') & (t.index <= '2020-06-30'))],
    'z>=2, drop 2020-03-12 only': t.drop(pd.Timestamp('2020-03-12'), errors='ignore'),
    'top 20% (z>=1.55), all': d[d.zL >= d.zL.quantile(.8)],
    'top 20%, ex-COVID': d[(d.zL >= d.zL.quantile(.8)) & ~((d.index >= '2020-02-15') & (d.index <= '2020-06-30'))],
}
for nm, tt in variants.items():
    for h in ['gap', 'd1', 'd5']:
        r = tail_diff(tt, h); r.update(variant=nm, horizon=h); tl.append(r)
TL = pd.DataFrame(tl)[['variant', 'horizon', 'n_e', 'n_n', 'diff', 'lo', 'hi', 'p_perm', 'med_e', 'med_n']]
TL.to_csv(f'{OUT}/tail_robust.csv', index=False); print(TL.round(2).to_string())

# d) up vs down asymmetric slopes
d['Lp'] = d.late.clip(lower=0); d['Ln'] = d.late.clip(upper=0)
asy = []
for h in ['gap', 'd1']:
    dd = d[d[h].notna()]
    X = pd.DataFrame({'const': 1.0, 'Lp': dd.Lp, 'Ln': dd.Ln, 'E': dd.E, 'E_Lp': dd.E * dd.Lp, 'E_Ln': dd.E * dd.Ln})
    m = sm.WLS(dd[h], X, weights=1 / dd.vol20 ** 2).fit(cov_type='HAC', cov_kwds={'maxlags': 10})
    for p in ['E_Lp', 'E_Ln']:
        asy.append(dict(horizon=h, term=p, coef=m.params[p], se=m.bse[p], p=m.pvalues[p]))
ASY = pd.DataFrame(asy); ASY.to_csv(f'{OUT}/asym.csv', index=False); print(ASY.round(3).to_string())

# e) simulated power: effect of delta = -0.5 / +0.5 reversal slope shift on hit-rate and regression
json.dump(res, open(f'{OUT}/diag.json', 'w'), indent=1, default=str)
