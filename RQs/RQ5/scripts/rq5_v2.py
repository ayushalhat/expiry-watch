"""RQ5 v2 additions (written after comparing against an independent analysis of the same data):
 A. same sign-matched reversal test at all seven horizons, Holm-adjusted
 B. control-reuse robustness: one-to-one matching without replacement, random processing order
 C. regime-by-regime table (all 12 regimes) and pre/post-reform difference-in-differences of the matched reversal gap
 D. relation to the unconditional reversal ratio RR = -(post-close move)/(late move) used elsewhere
"""
import json, sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np, pandas as pd
from scipy import stats
import rq5lib as L
import rq5_panel as P

OUT = sys.argv[1]
rng = np.random.default_rng(55)
s = P.build_panel()
d = pd.read_pickle(f'{OUT}/panel.pkl')            # sample: pre-CAS, features available, nonzero late move
HZ = [('gap', 'Next open'), ('b1', 'Next 11:15'), ('b2', 'Next 13:15'), ('d1', 'Next close'), ('d2', '+2 days'), ('d3', '+3 days'), ('d5', '+5 days')]
for h, _ in HZ:
    d['hit_' + h] = np.where(d[h].isna(), np.nan, (np.sign(d[h]) == -d.sgn).astype(float))
mc = L.match_controls(s, k=12, covs=('vol20', 'vol5', 'prev_abs'))

def sign_matched(hit, min_ctrl=3):
    rows = []
    for e, cs in mc.items():
        if e not in d.index or pd.isna(d.loc[e, hit]): continue
        c = d.reindex(cs); c = c[(c.sgn == d.loc[e, 'sgn']) & c[hit].notna()]
        if len(c) < min_ctrl: continue
        rows.append(dict(date=e, regime=s.loc[e, 'regime'], typ=s.loc[e, 'exp_type'], hit_e=d.loc[e, hit], hit_c=c[hit].mean()))
    return pd.DataFrame(rows).set_index('date')

def summ(g):
    x = g.hit_e - g.hit_c; n = len(x); m = x.mean(); se = x.std(ddof=1) / np.sqrt(n)
    return dict(n=n, rev_exp=100 * g.hit_e.mean(), rev_ctrl=100 * g.hit_c.mean(), diff_pp=100 * m, se_pp=100 * se, lo=100 * (m - 1.96 * se), hi=100 * (m + 1.96 * se),
                p=2 * (1 - stats.norm.cdf(abs(m / se))))

# ---- A ----
rows = []
for h, nm in HZ:
    r = summ(sign_matched('hit_' + h)); r['horizon'] = nm; rows.append(r)
A = pd.DataFrame(rows)[['horizon', 'n', 'rev_exp', 'rev_ctrl', 'diff_pp', 'lo', 'hi', 'p']]
# Holm
order = np.argsort(A.p.values); m = len(A); adj = np.empty(m); run = 0
for rank, i in enumerate(order):
    run = max(run, (m - rank) * A.p.values[i]); adj[i] = min(1, run)
A['p_holm'] = adj
A.to_csv(f'{OUT}/v2_horizons.csv', index=False); print(A.round(3).to_string())

# ---- B: one-to-one, no replacement, random order ----
dd = d.copy()
X = np.log(dd[['vol20', 'vol5', 'prev_abs']].clip(lower=1e-3)); ok = X.notna().all(axis=1); dd, X = dd[ok], X[ok]
cinv = np.linalg.pinv(np.cov(X.values.T))
def one_run(k, seed):
    r = np.random.default_rng(seed); out = []
    for rg, grp in dd.groupby('regime'):
        ex = grp[grp.E == 1].index.values.copy(); ct = grp[grp.E == 0]
        used = set(); r.shuffle(ex)
        for e in ex:
            if pd.isna(dd.loc[e, 'hit_gap']): continue
            cand = ct[(ct.sgn == dd.loc[e, 'sgn']) & ct.hit_gap.notna() & (~ct.index.isin(used))]
            if len(cand) < k: continue
            diff = X.loc[cand.index].values - X.loc[e].values
            dist = np.einsum('ij,jk,ik->i', diff, cinv, diff)
            pick = cand.index[np.argsort(dist)[:k]]; used.update(pick)
            out.append(dd.loc[e, 'hit_gap'] - dd.loc[pick, 'hit_gap'].mean())
    out = np.array(out); return 100 * out.mean(), 100 * out.std(ddof=1) / np.sqrt(len(out)), len(out)
rows = []
for k in (1, 2, 3):
    res = [one_run(k, 1000 * k + i) for i in range(60)]
    est = np.array([x[0] for x in res]); se = np.mean([x[1] for x in res]); n = int(np.mean([x[2] for x in res]))
    rows.append(dict(k_controls_per_expiry=k, n=n, diff_median=np.median(est), diff_p2_5=np.percentile(est, 2.5), diff_p97_5=np.percentile(est, 97.5), mean_se=se,
                     ci_lo=np.median(est) - 1.96 * se, ci_hi=np.median(est) + 1.96 * se, p=2 * (1 - stats.norm.cdf(abs(np.median(est) / se)))))
B = pd.DataFrame(rows); B.to_csv(f'{OUT}/v2_no_reuse.csv', index=False); print(B.round(2).to_string())

# ---- C: regimes and pre/post ----
S = sign_matched('hit_gap')
rows = []
for rg, g in S.groupby('regime'):
    r = summ(g) if len(g) > 2 else dict(n=len(g), rev_exp=100 * g.hit_e.mean(), rev_ctrl=100 * g.hit_c.mean(), diff_pp=100 * (g.hit_e - g.hit_c).mean(), se_pp=np.nan, lo=np.nan, hi=np.nan, p=np.nan)
    r['regime'] = rg; rows.append(r)
C = pd.DataFrame(rows)[['regime', 'n', 'rev_exp', 'rev_ctrl', 'diff_pp', 'se_pp']]; C.to_csv(f'{OUT}/v2_regimes.csv', index=False); print(C.round(1).to_string())
def period(dt): return 'pre' if dt < pd.Timestamp('2024-10-01') else ('tue' if dt >= pd.Timestamp('2025-09-01') else 'mid')
S['per'] = [period(x) for x in S.index]
rows = []
for p_ in ['pre', 'mid', 'tue']:
    g = S[S.per == p_]; r = summ(g); r['period'] = {'pre': 'Before Oct 2024', 'mid': 'Oct 2024 - Aug 2025', 'tue': 'Tuesday era'}[p_]; rows.append(r)
G = pd.DataFrame(rows)[['period', 'n', 'rev_exp', 'rev_ctrl', 'diff_pp', 'se_pp', 'lo', 'hi', 'p']]
post = S[S.per != 'pre']; pre = S[S.per == 'pre']
a, b = summ(post), summ(pre)
did = a['diff_pp'] - b['diff_pp']; se_did = np.hypot(a['se_pp'], b['se_pp'])
res = dict(did_post_vs_pre=did, did_se=se_did, did_lo=did - 1.96 * se_did, did_hi=did + 1.96 * se_did, did_p=2 * (1 - stats.norm.cdf(abs(did / se_did))),
           post=a, pre=b)
for nm, mask in [('ctrl_pre', pre.hit_c), ('ctrl_post', post.hit_c), ('exp_pre', pre.hit_e), ('exp_post', post.hit_e)]:
    res[nm] = 100 * mask.mean()
a2 = summ(S[S.per == 'tue']); did2 = a2['diff_pp'] - b['diff_pp']; se2 = np.hypot(a2['se_pp'], b['se_pp'])
res.update(did_tue_vs_pre=did2, did_tue_se=se2, did_tue_p=2 * (1 - stats.norm.cdf(abs(did2 / se2))))
G.to_csv(f'{OUT}/v2_periods.csv', index=False); print(G.round(2).to_string()); print({k: v for k, v in res.items() if not isinstance(v, dict)})

# ---- D: unconditional RR ----
dd2 = d[d.gap.notna()].copy(); dd2['RR'] = -dd2.gap / dd2.late
rows = []
for nm, g in [('Expiry', dd2[dd2.E == 1]), ('Normal days', dd2[dd2.E == 0])]:
    rows.append(dict(group=nm, n=len(g), med_RR=g.RR.median(), share_abs_RR_gt5=100 * (g.RR.abs() > 5).mean(), pct_reversal=100 * (g.RR > 0).mean(),
                     pct_gap_up=100 * (g.gap > 0).mean(), med_gap=g.gap.median(), mean_RR_clipped=g.RR.clip(-5, 5).mean()))
D = pd.DataFrame(rows); D.to_csv(f'{OUT}/v2_rr.csv', index=False); print(D.round(2).to_string())
mw = stats.mannwhitneyu(dd2[dd2.E == 1].RR, dd2[dd2.E == 0].RR).pvalue
fr = lambda g: 100 * ((g.gap > 0) == (g.sgn < 0)).mean()
res['rr_mw_p'] = float(mw)
up = dd2[dd2.sgn > 0]; dn = dd2[dd2.sgn < 0]
res['normal_rev_up_late'] = 100 * (up[up.E == 0].gap < 0).mean(); res['normal_rev_down_late'] = 100 * (dn[dn.E == 0].gap > 0).mean()
res['share_up_late_expiry'] = 100 * (dd2[dd2.E == 1].sgn > 0).mean()
json.dump(res, open(f'{OUT}/v2.json', 'w'), indent=1, default=str); print(json.dumps({k: v for k, v in res.items()}, indent=1, default=str)[:2500])
