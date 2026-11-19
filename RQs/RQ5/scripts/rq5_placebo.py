"""Placebo tests for the primary (sign-conditional matched) statistic."""
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
true_exp = s.is_exp.copy()
res = {}


def placebo(fake_mask, label, k=12, min_ctrl=3):
    s2 = s.copy()
    s2['is_exp'] = fake_mask.reindex(s2.index).fillna(False).values
    # remove true expiries from the control pool (their covariates -> NaN so they are never used)
    s2.loc[true_exp & ~s2.is_exp, 'vol20'] = np.nan
    mc = L.match_controls(s2, k=k)
    diffs = []
    for e, cs in mc.items():
        if e not in d.index or pd.isna(d.loc[e, 'hit_gap']): continue
        c = d.reindex(cs); c = c[(c.sgn == d.loc[e, 'sgn']) & c.hit_gap.notna()]
        if len(c) < min_ctrl: continue
        diffs.append(d.loc[e, 'hit_gap'] - c.hit_gap.mean())
    x = pd.Series(diffs)
    return dict(placebo=label, n=len(x), diff_pp=100 * x.mean(), se_pp=100 * x.std(ddof=1) / np.sqrt(len(x)))

rows = []
thu_era = s.index < '2025-09-01'
for wd, nm in [(0, 'Monday'), (1, 'Tuesday'), (2, 'Wednesday'), (4, 'Friday')]:
    m = pd.Series((s.index.weekday == wd) & thu_era & ~true_exp.values & ~s.post_cas.values, index=s.index)
    rows.append(placebo(m, f'{nm} treated as expiry (Thursday era)'))
# Tuesday era: non-expiry Thursdays as pseudo-expiry
m = pd.Series((s.index.weekday == 3) & (s.index >= '2025-09-01') & ~true_exp.values & ~s.post_cas.values, index=s.index)
rows.append(placebo(m, 'Non-expiry Thursday treated as expiry (Tuesday era)'))
PL = pd.DataFrame(rows); PL['lo'] = PL.diff_pp - 1.96 * PL.se_pp; PL['hi'] = PL.diff_pp + 1.96 * PL.se_pp
PL.to_csv(f'{OUT}/placebo_signmatched.csv', index=False); print(PL.round(2).to_string())

# random relabelling inside each regime, LPM interaction coefficient (drift-free), 3000 draws
d = d.copy(); d['up'] = (d.sgn > 0).astype(int); d['pos'] = (d.gap > 0).astype(float)
dd = d[d.gap.notna()].copy()
def e_up(E):
    X = np.column_stack([np.ones(len(dd)), E, dd.up.values, E * dd.up.values])
    return np.linalg.lstsq(X, dd.pos.values, rcond=None)[0][3]
obs = e_up(dd.E.values.astype(float))
rng = np.random.default_rng(5)
groups = [ix.values for _, ix in pd.Series(np.arange(len(dd)), index=dd.regime).groupby(level=0)]
E0 = dd.E.values.astype(float); null = []
for _ in range(3000):
    Ep = E0.copy()
    for g in groups: Ep[g] = rng.permutation(E0[g])
    null.append(e_up(Ep))
null = np.array(null)
res['perm_lpm'] = dict(obs_pp=float(100 * obs), null_sd_pp=float(100 * null.std()), p=float((np.abs(null) >= abs(obs)).mean()))
print(res)
json.dump(res, open(f'{OUT}/placebo.json', 'w'), indent=1)
