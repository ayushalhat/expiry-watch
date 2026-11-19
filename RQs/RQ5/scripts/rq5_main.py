import json, sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np, pandas as pd
import statsmodels.api as sm
import rq5lib as L
import rq5_panel as P

OUT = sys.argv[1]
H = P.HORIZONS
rng = np.random.default_rng(20261113)

s = P.build_panel()
d = P.sample(s)
res = {}
res['n_sessions'] = int(len(d))
res['n_exp'] = int(d.E.sum()); res['n_w'] = int(d.Ew.sum()); res['n_m'] = int(d.Em.sum())
print('sample', res)

# ---------- 0. noise and power context ----------
res['sd_gap_bps'] = float(d.gap.std()); res['sd_L_bps'] = float(d.late.std())
res['sd_L_exp'] = float(d[d.E == 1].late.std())
res['median_absgap'] = float(d.gap.abs().median())

# ---------- 1. Reversal hit-rate at next open ----------
d = d.copy()
d['hit_gap'] = (np.sign(d.gap) == -d.sgn).astype(float)
d.loc[d.gap.isna(), 'hit_gap'] = np.nan
res['hit_all'] = float(d.hit_gap.mean())
res['hit_nonexp'] = float(d[d.E == 0].hit_gap.mean())
for nm, m in [('weekly', d.Ew == 1), ('monthly', d.Em == 1), ('exp', d.E == 1)]:
    g = d[m & d.hit_gap.notna()]
    res[f'hit_{nm}'] = float(g.hit_gap.mean()); res[f'hit_{nm}_n'] = int(len(g))

# matched controls (3 per expiry, within regime, Mahalanobis on log vol20, vol5, |prev-day move|)
mc = L.match_controls(s)
rows = []
for e, cs in mc.items():
    if e not in d.index: continue
    c = d.reindex(cs)
    rows.append(dict(date=e, typ=s.loc[e, 'exp_type'], qe=bool(s.loc[e, 'quarter_end']),
                     hit_e=d.loc[e, 'hit_gap'], hit_c=c.hit_gap.mean(),
                     **{f'Y_{h}_e': d.loc[e, f'Y_{h}'] for h in H},
                     **{f'Y_{h}_c': c[f'Y_{h}'].mean() for h in H},
                     absL_e=d.loc[e, 'absL'], absL_c=c.absL.mean(),
                     z_e=d.loc[e, 'zL'], gap_e=d.loc[e, 'gap'], L_e=d.loc[e, 'late']))
M = pd.DataFrame(rows).set_index('date')
M['year'] = M.index.year
M.to_csv(f'{OUT}/matched_pairs.csv')
res['n_matched'] = int(len(M))


def mean_ci(x):
    x = x.dropna().values
    n = len(x); m = x.mean(); se = x.std(ddof=1) / np.sqrt(n)
    return m, se, n

tab = []
for nm, m in [('Weekly', M.typ == 'weekly'), ('Monthly', M.typ == 'monthly'), ('All expiries', M.typ.notna())]:
    g = M[m]
    dd = (g.hit_e - g.hit_c).dropna()
    mm, se, n = mean_ci(dd)
    tab.append(dict(group=nm, n=n, hit_exp=g.hit_e.mean(), hit_ctrl=g.hit_c.mean(), diff_pp=100 * mm, se_pp=100 * se,
                    lo=100 * (mm - 1.96 * se), hi=100 * (mm + 1.96 * se)))
HIT = pd.DataFrame(tab); HIT.to_csv(f'{OUT}/hit_rates.csv', index=False)
print(HIT.round(3).to_string())

# binomial test of expiry hit-rate vs 50%
from scipy import stats
for nm in ['exp', 'weekly', 'monthly']:
    k = int(round(res[f'hit_{nm}'] * res[f'hit_{nm}_n']))
    res[f'binom_p_{nm}'] = float(stats.binomtest(k, res[f'hit_{nm}_n'], 0.5).pvalue)

# ---------- 2. Interaction regression (WLS, HAC) ----------
def design(df, spec):
    X = pd.DataFrame({'const': 1.0, 'L': df.late})
    if spec == 'pooled':
        X['E'] = df.E; X['E_L'] = df.E * df.late
    else:
        X['Ew'] = df.Ew; X['Em'] = df.Em; X['Ew_L'] = df.Ew * df.late; X['Em_L'] = df.Em * df.late
    return X


def fit(df, h, spec, weighted=True, maxlags=10):
    dd = df[df[h].notna()]
    X = design(dd, spec); y = dd[h]
    w = 1.0 / dd.vol20 ** 2 if weighted else None
    m = (sm.WLS(y, X, weights=w) if weighted else sm.OLS(y, X)).fit(cov_type='HAC', cov_kwds={'maxlags': maxlags})
    return m, len(dd)

reg_rows = []
for spec in ['pooled', 'split']:
    for h in H:
        m, n = fit(d, h, spec)
        for p in m.params.index:
            reg_rows.append(dict(spec=spec, horizon=h, term=p, coef=m.params[p], se=m.bse[p], t=m.tvalues[p], p=m.pvalues[p], n=n))
REG = pd.DataFrame(reg_rows); REG.to_csv(f'{OUT}/regression.csv', index=False)
print(REG[REG.term.isin(['L', 'E_L', 'Ew_L', 'Em_L'])].round(3).to_string())

# OLS (unweighted) comparison, and winsorised-at-1% version, pooled only
alt = []
for label, df_ in [('WLS', d), ('OLS', d)]:
    for h in H:
        m, n = fit(df_, h, 'pooled', weighted=(label == 'WLS'))
        alt.append(dict(version=label, horizon=h, base_L=m.params['L'], E_L=m.params['E_L'], E_L_se=m.bse['E_L'], n=n))
dw = d.copy()
for c in ['late'] + H:
    lo, hi = dw[c].quantile([0.01, 0.99]); dw[c] = dw[c].clip(lo, hi)
for h in H:
    m, n = fit(dw, h, 'pooled', weighted=True)
    alt.append(dict(version='WLS winsor1%', horizon=h, base_L=m.params['L'], E_L=m.params['E_L'], E_L_se=m.bse['E_L'], n=n))
d_ex20 = d[~((d.index >= '2020-02-15') & (d.index <= '2020-06-30'))]
for h in H:
    m, n = fit(d_ex20, h, 'pooled', weighted=True)
    alt.append(dict(version='WLS ex-COVID (15Feb-30Jun 2020)', horizon=h, base_L=m.params['L'], E_L=m.params['E_L'], E_L_se=m.bse['E_L'], n=n))
ALT = pd.DataFrame(alt); ALT.to_csv(f'{OUT}/regression_robust.csv', index=False)
print(ALT.round(3).to_string())

# ---------- 3. Tail (large late moves): zL = |L| / trailing-20d mean |L| ----------
res['z_p80'] = float(d.zL.quantile(.8)); res['z_p90'] = float(d.zL.quantile(.9))
tail_rows = []
for thr_name, thr in [('z>=2', 2.0), ('top20%', d.zL.quantile(.8)), ('top10%', d.zL.quantile(.9))]:
    t = d[d.zL >= thr]
    for grp, m in [('Expiry', t.E == 1), ('Non-expiry', t.E == 0), ('Monthly exp.', t.Em == 1), ('Weekly exp.', t.Ew == 1)]:
        g = t[m]
        r = dict(thr=thr_name, group=grp, n=len(g), meanL=g.absL.mean())
        for h in ['gap', 'd1', 'd5']:
            x = g[f'Y_{h}'].dropna()
            r[f'rev_{h}_bps'] = x.mean(); r[f'rev_{h}_se'] = x.std(ddof=1) / np.sqrt(len(x)) if len(x) > 1 else np.nan
            r[f'rev_{h}_share'] = x.mean() / g.absL.mean()
        r['hit_gap'] = g.hit_gap.mean()
        tail_rows.append(r)
TAIL = pd.DataFrame(tail_rows); TAIL.to_csv(f'{OUT}/tail.csv', index=False)
print(TAIL.round(3).to_string())

# permutation test for expiry-vs-non-expiry difference in mean Y_gap within the z>=2 tail
t = d[d.zL >= 2.0]
obs = {}
for h in ['gap', 'd1', 'd5']:
    a = t[(t.E == 1)][f'Y_{h}'].dropna(); b = t[t.E == 0][f'Y_{h}'].dropna()
    obs[h] = a.mean() - b.mean()
    perm = []
    allv = pd.concat([a, b]).to_numpy(copy=True)
    for _ in range(5000):
        rng.shuffle(allv); perm.append(allv[:len(a)].mean() - allv[len(a):].mean())
    res[f'tail_perm_{h}'] = dict(diff=float(obs[h]), p=float((np.abs(perm) >= abs(obs[h])).mean()), n_exp=int(len(a)), n_non=int(len(b)))
print({k: v for k, v in res.items() if k.startswith('tail_perm')})

# ---------- 4. Subgroups: pooled interaction by group ----------
sub_rows = []
def run_sub(label, df_):
    for h in ['gap', 'd1', 'd5']:
        dd = df_[df_[h].notna()]
        if dd.E.sum() < 8: continue
        m, n = fit(df_, h, 'pooled')
        sub_rows.append(dict(group=label, horizon=h, n_exp=int(dd.E.sum()), E_L=m.params['E_L'], se=m.bse['E_L'], p=m.pvalues['E_L']))
run_sub('All', d)
run_sub('2019-22', d[d.index < '2023-01-01'])
run_sub('2023-26', d[d.index >= '2023-01-01'])
# subgroup by expiry type vs all non-expiry (re-use split spec)
for h in ['gap', 'd1', 'd5']:
    m, n = fit(d, h, 'split')
    sub_rows.append(dict(group='Weekly only', horizon=h, n_exp=int(d[d[h].notna()].Ew.sum()), E_L=m.params['Ew_L'], se=m.bse['Ew_L'], p=m.pvalues['Ew_L']))
    sub_rows.append(dict(group='Monthly', horizon=h, n_exp=int(d[d[h].notna()].Em.sum()), E_L=m.params['Em_L'], se=m.bse['Em_L'], p=m.pvalues['Em_L']))
    # dose-response: monthly minus weekly (same weekday)
    cv = m.cov_params()
    diff = m.params['Em_L'] - m.params['Ew_L']
    se = np.sqrt(cv.loc['Em_L', 'Em_L'] + cv.loc['Ew_L', 'Ew_L'] - 2 * cv.loc['Em_L', 'Ew_L'])
    sub_rows.append(dict(group='Monthly minus weekly', horizon=h, n_exp=int(d[d[h].notna()].E.sum()), E_L=diff, se=se, p=2 * (1 - stats.norm.cdf(abs(diff / se)))))
# quarter-end monthly
dq = d.copy(); dq['Eq'] = (dq.quarter_end).astype(int); dq['E_nq'] = ((dq.E == 1) & (dq.Eq == 0)).astype(int)
for h in ['gap', 'd1', 'd5']:
    dd = dq[dq[h].notna()]
    X = pd.DataFrame({'const': 1.0, 'L': dd.late, 'E_nq': dd.E_nq, 'Eq': dd.Eq, 'E_nq_L': dd.E_nq * dd.late, 'Eq_L': dd.Eq * dd.late})
    m = sm.WLS(dd[h], X, weights=1 / dd.vol20 ** 2).fit(cov_type='HAC', cov_kwds={'maxlags': 10})
    sub_rows.append(dict(group='Quarter-end monthly', horizon=h, n_exp=int(dd.Eq.sum()), E_L=m.params['Eq_L'], se=m.bse['Eq_L'], p=m.pvalues['Eq_L']))
# Tuesday era: Tuesday expiries vs non-expiry sessions inside the Tuesday era; and falsification: non-expiry Thursdays after Sep 2025
tue = d[d.index >= '2025-09-01']
for h in ['gap', 'd1']:
    dd = tue[tue[h].notna()]
    X = pd.DataFrame({'const': 1.0, 'L': dd.late, 'E': dd.E, 'E_L': dd.E * dd.late})
    m = sm.WLS(dd[h], X, weights=1 / dd.vol20 ** 2).fit(cov_type='HAC', cov_kwds={'maxlags': 5})
    sub_rows.append(dict(group='Tuesday era only (Sep25-Jul26)', horizon=h, n_exp=int(dd.E.sum()), E_L=m.params['E_L'], se=m.bse['E_L'], p=m.pvalues['E_L']))
    dd = dd.copy(); dd['Thu'] = (dd.index.weekday == 3).astype(int)
    X = pd.DataFrame({'const': 1.0, 'L': dd.late, 'Thu': dd.Thu, 'Thu_L': dd.Thu * dd.late, 'E': dd.E, 'E_L': dd.E * dd.late})
    m = sm.WLS(dd[h], X, weights=1 / dd.vol20 ** 2).fit(cov_type='HAC', cov_kwds={'maxlags': 5})
    sub_rows.append(dict(group='Tuesday era: non-expiry Thursday (placebo)', horizon=h, n_exp=int(dd.Thu.sum()), E_L=m.params['Thu_L'], se=m.bse['Thu_L'], p=m.pvalues['Thu_L']))
SUB = pd.DataFrame(sub_rows); SUB.to_csv(f'{OUT}/subgroups.csv', index=False)
print(SUB.round(3).to_string())

# ---------- 5. Placebo A: fake expiry on other weekdays (Thursday era, same weeks) ----------
thu = d[d.index < '2025-09-01']
plc = []
exp_dates = set(s.index[s.is_exp])
for wd, nm in [(0, 'Mon'), (1, 'Tue'), (2, 'Wed'), (4, 'Fri')]:
    sel = thu[(thu.index.weekday == wd) & (thu.E == 0)]
    dd = thu[(thu.E == 0)].copy()
    dd['F'] = (dd.index.weekday == wd).astype(int)
    for h in ['gap', 'd1']:
        x = dd[dd[h].notna()]
        X = pd.DataFrame({'const': 1.0, 'L': x.late, 'F': x.F, 'F_L': x.F * x.late})
        m = sm.WLS(x[h], X, weights=1 / x.vol20 ** 2).fit(cov_type='HAC', cov_kwds={'maxlags': 10})
        plc.append(dict(placebo=f'{nm} treated as expiry', horizon=h, n=int(x.F.sum()), coef=m.params['F_L'], se=m.bse['F_L'], p=m.pvalues['F_L']))
PLC = pd.DataFrame(plc); PLC.to_csv(f'{OUT}/placebo_weekday.csv', index=False)
print(PLC.round(3).to_string())

# ---------- 6. Placebo B: random relabelling within regime (calibration of HAC SEs) ----------
def delta_pooled(df_, h):
    dd = df_[df_[h].notna()]
    X = np.column_stack([np.ones(len(dd)), dd.late.values, dd.E.values, (dd.E * dd.late).values])
    w = 1 / dd.vol20.values ** 2
    sw = np.sqrt(w)
    beta = np.linalg.lstsq(X * sw[:, None], dd[h].values * sw, rcond=None)[0]
    return beta[3]

perm_res = {}
for h in ['gap', 'd1', 'd5']:
    obs_h = delta_pooled(d, h)
    null = []
    dd = d.copy()
    groups = [ix.values for _, ix in pd.Series(np.arange(len(dd)), index=dd.regime).groupby(level=0)]
    E0 = dd.E.values.copy()
    for _ in range(1500):
        Ep = E0.copy()
        for g in groups:
            Ep[g] = rng.permutation(E0[g])
        dd['E'] = Ep
        null.append(delta_pooled(dd, h))
    null = np.array(null)
    perm_res[h] = dict(obs=float(obs_h), null_sd=float(null.std()), p=float((np.abs(null) >= abs(obs_h)).mean()))
    dd['E'] = E0
res['perm_label'] = perm_res
print(perm_res)

# ---------- 7. Power / MDE ----------
m, n = fit(d, 'gap', 'pooled')
res['mde_gap'] = float(2.8 * m.bse['E_L'])
m5, n5 = fit(d, 'd5', 'pooled')
res['mde_d5'] = float(2.8 * m5.bse['E_L'])
res['mde_hit_pp'] = float(2.8 * 100 * np.sqrt(0.25 / res['hit_exp_n'] + 0.25 / (res['n_sessions'] - res['n_exp'])))

# ---------- 8. Case table: most extreme expiry late moves ----------
ev = pd.read_excel(L.XLSX, sheet_name='Events')
ev['Date'] = pd.to_datetime(ev['Date'], errors='coerce')
ev = ev.dropna(subset=['Date'])
ev_dates = set(ev.loc[ev['Overlap with NIFTY Expiry'].astype(str).str.upper() == 'Y', 'Date'])
ex = d[d.E == 1].sort_values('zL', ascending=False).head(12)
case = pd.DataFrame({'type': ex.exp_type, 'late_bps': ex.late.round(1), 'z': ex.zL.round(1), 'gap_bps': ex.gap.round(1),
                     'rev_gap_bps': ex.Y_gap.round(1), 'rev_d1_bps': ex.Y_d1.round(1), 'news_overlap': [i in ev_dates for i in ex.index]})
case.to_csv(f'{OUT}/cases.csv'); print(case.to_string())
res['events_overlap_expiry'] = [str(x.date()) for x in sorted(ev_dates)]

# ---------- 9. Event-time path data for figure ----------
def path(df_):
    r = pd.DataFrame({
        'pre_1515': -df_.sgn * np.log(df_.O4 / df_.O4) * 1e4,
        'close': df_.sgn * df_.late,
        'open+1': df_.sgn * (df_.late - (-df_.gap) * 0 + df_.gap),
    })
    base = df_.sgn
    pts = {
        '15:15 (start of last bar)': 0 * df_.late,
        'Close 15:30': base * df_.late,
        'Next open': base * (df_.late + df_.gap),
        'Next 11:15': base * (df_.late + df_.b1),
        'Next 13:15': base * (df_.late + df_.b2),
        'Next close': base * (df_.late + df_.d1),
        '+2d close': base * (df_.late + df_.d2),
        '+5d close': base * (df_.late + df_.d5),
    }
    return pd.DataFrame(pts)
PATH_E = path(d[(d.zL >= 2) & (d.E == 1)]); PATH_N = path(d[(d.zL >= 2) & (d.E == 0)])
pe = pd.DataFrame({'mean': PATH_E.mean(), 'se': PATH_E.std() / np.sqrt(PATH_E.count()), 'n': PATH_E.count()})
pn = pd.DataFrame({'mean': PATH_N.mean(), 'se': PATH_N.std() / np.sqrt(PATH_N.count()), 'n': PATH_N.count()})
pe.to_csv(f'{OUT}/path_expiry.csv'); pn.to_csv(f'{OUT}/path_nonexpiry.csv')
print(pe.round(2)); print(pn.round(2))

# ---------- 10. Hit-rate diagnostics: by sign of late move; alternative matching rules ----------
M2 = M.copy()
M2['L_sign'] = np.sign(M2.L_e)
sg = []
for nm, g in [('Late move up', M2[M2.L_sign > 0]), ('Late move down', M2[M2.L_sign < 0])]:
    dd = (g.hit_e - g.hit_c).dropna()
    mm, se, n = mean_ci(dd)
    sg.append(dict(group=nm, n=n, hit_exp=g.hit_e.mean(), hit_ctrl=g.hit_c.mean(), diff_pp=100 * mm, se_pp=100 * se))
SG = pd.DataFrame(sg); SG.to_csv(f'{OUT}/hit_by_sign.csv', index=False); print(SG.round(3).to_string())
res['share_up_exp'] = float((d[d.E == 1].late > 0).mean()); res['share_up_non'] = float((d[d.E == 0].late > 0).mean())
res['mean_gap_exp'] = float(d[d.E == 1].gap.mean()); res['mean_gap_non'] = float(d[d.E == 0].gap.mean())

alt_rows = []
for nm, covs, k in [('default (vol20, vol5, |prev day|), k=3', ('vol20', 'vol5', 'prev_abs'), 3),
                    ('vol20 only, k=3', ('vol20',), 3),
                    ('5 covariates, k=3', ('vol20', 'range5', 'ret5', 'prev_abs', 'firstbars_vol'), 3),
                    ('default, k=5', ('vol20', 'vol5', 'prev_abs'), 5),
                    ('default, k=10', ('vol20', 'vol5', 'prev_abs'), 10)]:
    mm_ = L.match_controls(s, k=k, covs=covs)
    dif = []
    for e, cs in mm_.items():
        if e not in d.index or pd.isna(d.loc[e, 'hit_gap']): continue
        c = d.reindex(cs).hit_gap
        dif.append(d.loc[e, 'hit_gap'] - c.mean())
    dif = pd.Series(dif)
    alt_rows.append(dict(matching=nm, n=len(dif), diff_pp=100 * dif.mean(), se_pp=100 * dif.std(ddof=1) / np.sqrt(len(dif))))
ALTM = pd.DataFrame(alt_rows); ALTM.to_csv(f'{OUT}/hit_matching_robust.csv', index=False); print(ALTM.round(2).to_string())
# all non-expiry sessions as the comparison (no matching): two-proportion z-test
a = d[(d.E == 1) & d.hit_gap.notna()].hit_gap; b = d[(d.E == 0) & d.hit_gap.notna()].hit_gap
zst = (a.mean() - b.mean()) / np.sqrt(a.mean() * (1 - a.mean()) / len(a) + b.mean() * (1 - b.mean()) / len(b))
res['hit_unmatched'] = dict(exp=float(a.mean()), non=float(b.mean()), z=float(zst), p=float(2 * (1 - stats.norm.cdf(abs(zst)))))

# ---------- 11. Control for the day's own trend (known by 15:15) ----------
d['T'] = np.log(d.C3 / d.O1) * 1e4
ctl = []
for h in ['gap', 'b2', 'd1', 'd5']:
    dd = d[d[h].notna()]
    X = pd.DataFrame({'const': 1.0, 'L': dd.late, 'E': dd.E, 'E_L': dd.E * dd.late, 'T': dd['T'], 'E_T': dd.E * dd['T'], 'LxT': dd.late * dd['T'] / 100})
    m = sm.WLS(dd[h], X, weights=1 / dd.vol20 ** 2).fit(cov_type='HAC', cov_kwds={'maxlags': 10})
    ctl.append(dict(horizon=h, E_L=m.params['E_L'], se=m.bse['E_L'], p=m.pvalues['E_L'], n=len(dd)))
CTL = pd.DataFrame(ctl); CTL.to_csv(f'{OUT}/regression_trend_control.csv', index=False); print(CTL.round(3).to_string())
# how often does the late move agree with the day's trend, expiry vs not
d['aligned'] = (np.sign(d['T']) == d.sgn).astype(int)
res['aligned_exp'] = float(d[d.E == 1].aligned.mean()); res['aligned_non'] = float(d[d.E == 0].aligned.mean())

json.dump(res, open(f'{OUT}/results.json', 'w'), indent=1, default=str)
d.to_pickle(f'{OUT}/panel.pkl')
print(json.dumps({k: v for k, v in res.items() if k not in ('events_overlap_expiry',)}, indent=1, default=str))
