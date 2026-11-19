import json, sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np, pandas as pd
import statsmodels.api as sm
from scipy import stats
import rq8lib as R
import rq5lib as L

OUT = sys.argv[1]
rng = np.random.default_rng(20261114)
res = {}
s = R.base_sessions()
E = R.expiry_table(s)
Epre = E[E.period != 'P4'].copy()          # pre-CAS expiries: P0-P3 (last-bar metrics comparable)
Epost = E[E.period == 'P4']
Epre['post'] = (Epre.index >= R.D1).astype(int)
Epre['tue'] = (Epre.index >= R.D2).astype(int)
res['n_pre'] = int(len(Epre)); res['n_cas'] = int(len(Epost))


def boot_med(x, B=4000):
    x = np.asarray(x, float); x = x[~np.isnan(x)]
    bs = np.median(rng.choice(x, (B, len(x))), axis=1)
    return np.median(x), np.percentile(bs, 2.5), np.percentile(bs, 97.5)


def wilson(k, n, z=1.96):
    if n == 0: return np.nan, np.nan
    p = k / n; den = 1 + z * z / n
    c = (p + z * z / (2 * n)) / den; h = z * np.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / den
    return c - h, c + h


def perm_median_diff(a, b, B=10000):
    a = np.asarray(a, float); b = np.asarray(b, float)
    obs = np.median(a) - np.median(b)
    allv = np.concatenate([a, b]); n = len(a); cnt = 0
    for _ in range(B):
        rng.shuffle(allv)
        if abs(np.median(allv[:n]) - np.median(allv[n:])) >= abs(obs) - 1e-12: cnt += 1
    return obs, cnt / B


# ---------------- A. Period and regime tables ----------------
rows = []
for p, g in E.groupby('period'):
    me = boot_med(g.EVR); ml = boot_med(g.L15R)
    kl, ke, kz = int(g.alert_L.sum()), int(g.alert_E.sum()), int(g.alert_z.sum()); n = len(g)
    rows.append(dict(period=p, n=n, weekly=int((g.type == 'weekly').sum()), monthly=int((g.type == 'monthly').sum()),
                     EVR_med=me[0], EVR_lo=me[1], EVR_hi=me[2], EVR_mean=g.EVR.mean(),
                     L15R_med=ml[0], L15R_lo=ml[1], L15R_hi=ml[2], L15R_mean=g.L15R.mean(),
                     absL_med=g.absL.median(),
                     alertL=100 * kl / n, alertL_lo=100 * wilson(kl, n)[0], alertL_hi=100 * wilson(kl, n)[1],
                     alertE=100 * ke / n, alertE_lo=100 * wilson(ke, n)[0], alertE_hi=100 * wilson(ke, n)[1],
                     alertZ=100 * kz / n, vol20_med=g.vol20.median()))
PT = pd.DataFrame(rows); PT.to_csv(f'{OUT}/period_table.csv', index=False)
print(PT.round(2).to_string())

sheet = pd.read_excel(L.XLSX, sheet_name='Regimes', header=0).iloc[:14]
sheet = sheet[sheet['Regime ID'].astype(str).str.startswith('R')].set_index('Regime ID')
rg = E.groupby('regime').agg(n=('EVR', 'size'), EVR_mean=('EVR', 'mean'), EVR_med=('EVR', 'median'), L15R_med=('L15R', 'median'),
                             alertL=('alert_L', 'mean'), alertE=('alert_E', 'mean'))
rg['alertL'] *= 100; rg['alertE'] *= 100
rg['sheet_mean_EVR'] = sheet['Mean_EVR'].astype(float); rg['start'] = sheet['Start Date']; rg['lot'] = sheet['NIFTY Weekly Lot']
rg.to_csv(f'{OUT}/regime_table.csv'); print(rg.round(2).to_string())
res['tieout_corr'] = float(rg.loc[[r for r in rg.index if r != 'R13'], ['EVR_mean', 'sheet_mean_EVR']].corr().iloc[0, 1])

# ---------------- B. Naive before/after (context only; trend not removed) ----------------
nv = []
pre = Epre[Epre.period == 'P0']; postall = Epre[Epre.period.isin(['P1', 'P2', 'P3'])]
for lab, g in [('Post-reform P1-P3 vs P0', postall), ('P1 vs P0', Epre[Epre.period == 'P1']), ('P2 vs P0', Epre[Epre.period == 'P2']), ('P3 (Tuesday) vs P0', Epre[Epre.period == 'P3'])]:
    for y, nm in [('lE', 'log EVR'), ('lL', 'log L15R')]:
        d_, p_ = perm_median_diff(g[y], pre[y])
        nv.append(dict(contrast=lab, outcome=nm, n_post=len(g), n_pre=len(pre), median_diff=d_, ratio=np.exp(d_), perm_p=p_,
                       mw_p=stats.mannwhitneyu(g[y], pre[y]).pvalue))
    for y, nm in [('alert_L', 'L15R>3'), ('alert_E', 'EVR>2.7')]:
        a = [[g[y].sum(), len(g) - g[y].sum()], [pre[y].sum(), len(pre) - pre[y].sum()]]
        nv.append(dict(contrast=lab, outcome=nm, n_post=len(g), n_pre=len(pre), median_diff=100 * (g[y].mean() - pre[y].mean()), ratio=np.nan,
                       perm_p=stats.fisher_exact(a)[1], mw_p=np.nan))
NV = pd.DataFrame(nv); NV.to_csv(f'{OUT}/naive_before_after.csv', index=False); print(NV.round(3).to_string())

# ---------------- C. Interrupted time series ----------------
def its(df, y, slopes=False, lpm=False, maxlags=4, quant=False):
    t = df.t.values
    X = pd.DataFrame({'const': 1.0, 't': t, 'D1': df.post.astype(float).values, 'D2': df.tue.astype(float).values}, index=df.index)
    if slopes:
        X['t_D1'] = (t - (R.D1 - R.T0).days / 365.25) * X.D1; X['t_D2'] = (t - (R.D2 - R.T0).days / 365.25) * X.D2
    if quant:
        m = sm.QuantReg(df[y], X).fit(q=0.5)
        return m
    return sm.OLS(df[y], X).fit(cov_type='HAC', cov_kwds={'maxlags': maxlags})

def its_rows(df, label):
    out = []
    for y, nm in [('lE', 'log EVR'), ('lL', 'log L15R'), ('alert_L', 'alert L15R>3 (LPM)'), ('alert_E', 'alert EVR>2.7 (LPM)')]:
        for spec, kw in [('levels', dict()), ('levels+slopes', dict(slopes=True))]:
            m = its(df, y, **kw)
            for term in ['t', 'D1', 'D2'] + (['t_D1', 't_D2'] if kw.get('slopes') else []):
                out.append(dict(sample=label, outcome=nm, spec=spec, term=term, coef=m.params[term], se=m.bse[term], p=m.pvalues[term],
                                lo=m.params[term] - 1.96 * m.bse[term], hi=m.params[term] + 1.96 * m.bse[term], n=len(df)))
    for y, nm in [('lE', 'log EVR'), ('lL', 'log L15R')]:
        m = its(df, y, quant=True)
        for term in ['t', 'D1', 'D2']:
            out.append(dict(sample=label, outcome=nm, spec='median regression', term=term, coef=m.params[term], se=m.bse[term], p=m.pvalues[term],
                            lo=m.params[term] - 1.96 * m.bse[term], hi=m.params[term] + 1.96 * m.bse[term], n=len(df)))
    return out
ITS = pd.DataFrame(its_rows(Epre, 'all expiries') + its_rows(Epre[Epre.type == 'weekly'], 'weekly') + its_rows(Epre[Epre.type == 'monthly'], 'monthly'))
ITS.to_csv(f'{OUT}/its.csv', index=False)
print(ITS[(ITS['sample'] == 'all expiries') & (ITS.spec != 'levels+slopes')].round(3).to_string())

# ---------------- D. Local windows (26 expiries each side) ----------------
def local_window(df, brk, y, w=26, binary=False):
    pre = df[df.index < brk].tail(w); post = df[df.index >= brk].head(w)
    if binary:
        a = [[post[y].sum(), len(post) - post[y].sum()], [pre[y].sum(), len(pre) - pre[y].sum()]]
        return dict(n_pre=len(pre), n_post=len(post), pre=100 * pre[y].mean(), post=100 * post[y].mean(), diff=100 * (post[y].mean() - pre[y].mean()),
                    p=stats.fisher_exact(a)[1], lo=np.nan, hi=np.nan)
    d_, p_ = perm_median_diff(post[y], pre[y])
    bs = [np.median(rng.choice(post[y].values, len(post))) - np.median(rng.choice(pre[y].values, len(pre))) for _ in range(4000)]
    return dict(n_pre=len(pre), n_post=len(post), pre=np.median(pre[y]), post=np.median(post[y]), diff=d_, p=p_, lo=np.percentile(bs, 2.5), hi=np.percentile(bs, 97.5))

lw = []
for brk, bn in [(R.D1, 'D1 2024-10-01'), (R.D2, 'D2 2025-09-01')]:
    for y, nm, b in [('lE', 'log EVR', False), ('lL', 'log L15R', False), ('alert_L', 'L15R>3 %', True), ('alert_E', 'EVR>2.7 %', True)]:
        r = local_window(Epre, brk, y, binary=b); r.update(brk=bn, outcome=nm); lw.append(r)
LW = pd.DataFrame(lw); LW.to_csv(f'{OUT}/local_windows.csv', index=False); print(LW.round(3).to_string())

# ---------------- E. Scan of all break points (null calibration) ----------------
w = 26
scan = []
for i in range(w, len(Epre) - w + 1):
    pre_ = Epre.iloc[i - w:i]; post_ = Epre.iloc[i:i + w]
    scan.append(dict(date=Epre.index[i], dL=np.median(post_.lL) - np.median(pre_.lL), dE=np.median(post_.lE) - np.median(pre_.lE),
                     dAL=100 * (post_.alert_L.mean() - pre_.alert_L.mean())))
SC = pd.DataFrame(scan).set_index('date'); SC.to_csv(f'{OUT}/scan.csv')
for brk, bn in [(R.D1, 'D1'), (R.D2, 'D2')]:
    row = SC[SC.index >= brk].iloc[0]
    for c in ['dL', 'dE', 'dAL']:
        v = row[c]; pct = (np.abs(SC[c]) >= abs(v)).mean()
        res[f'scan_{bn}_{c}'] = dict(value=float(v), share_of_breaks_as_extreme=float(pct), n_breaks=int(len(SC)), date=str(row.name.date()))
print({k: v for k, v in res.items() if k.startswith('scan')})

# ---------------- F. Relocation ----------------
# F1: per-bar ratio profile, pre vs post reform
bar = []
for lab, g in [('Pre-reform (P0)', Epre[Epre.period == 'P0']), ('Post-reform (P1-P3)', Epre[Epre.period.isin(['P1', 'P2', 'P3'])]),
               ('P1', Epre[Epre.period == 'P1']), ('P2', Epre[Epre.period == 'P2']), ('P3 Tuesday', Epre[Epre.period == 'P3'])]:
    for i, bl in zip(range(1, 5), ['09:15-11:15', '11:15-13:15', '13:15-15:15', '15:15-15:30']):
        m = boot_med(g[f'b{i}R']); bar.append(dict(group=lab, bar=bl, n=len(g), med=m[0], lo=m[1], hi=m[2], mean=g[f'b{i}R'].mean()))
BAR = pd.DataFrame(bar); BAR.to_csv(f'{OUT}/bar_profile.csv', index=False); print(BAR[BAR.group.isin(['Pre-reform (P0)', 'Post-reform (P1-P3)'])].round(2).to_string())
bt = []
for i in range(1, 5):
    d_, p_ = perm_median_diff(np.log(postall[f'b{i}R']), np.log(pre[f'b{i}R']))
    bt.append(dict(bar=i, log_median_diff=d_, ratio=np.exp(d_), perm_p=p_))
BT = pd.DataFrame(bt); BT.to_csv(f'{OUT}/bar_tests.csv', index=False); print(BT.round(3).to_string())

# F2: weekday profile (all regular pre-CAS sessions), Thursday era vs Tuesday era
S = s[(~s.post_cas) & s.zL.notna() & s.relRV.notna()].copy()
S['era'] = np.where(S.index >= R.D2, 'Tue', 'Thu'); S['wd'] = S.index.weekday; S['wk'] = S.index.to_period('W-SUN')
tab = S.groupby(['era', 'wd']).agg(n=('zL', 'size'), zL_mean=('zL', 'mean'), zL_med=('zL', 'median'), relRV_mean=('relRV', 'mean'), relRV_med=('relRV', 'median')).round(3)
tab.to_csv(f'{OUT}/weekday_profile.csv'); print(tab.to_string())

def contrasts(df):
    out = {}
    for m_ in ['zL', 'relRV']:
        def gap(sub, wd):
            return sub[sub.wd == wd][m_].mean() - sub[sub.wd != wd][m_].mean()
        th = df[df.era == 'Thu']; tu = df[df.era == 'Tue']
        out[f'{m_}: Thursday vs other days, Thursday era'] = gap(th, 3)
        out[f'{m_}: Tuesday vs other days, Tuesday era'] = gap(tu, 1)
        out[f'{m_}: Thursday vs other days, Tuesday era'] = gap(tu, 3)
        out[f'{m_}: Tuesday vs other days, Thursday era'] = gap(th, 1)
    return out
obs = contrasts(S)
weeks = {era: [g for _, g in S[S.era == era].groupby('wk')] for era in ['Thu', 'Tue']}
bs = {k: [] for k in obs}
for _ in range(1500):
    d = pd.concat([weeks[era][i] for era in ['Thu', 'Tue'] for i in rng.integers(0, len(weeks[era]), len(weeks[era]))])
    c = contrasts(d)
    for k in obs: bs[k].append(c[k])
WK = pd.DataFrame([dict(contrast=k, est=v, lo=np.percentile(bs[k], 2.5), hi=np.percentile(bs[k], 97.5)) for k, v in obs.items()])
WK.to_csv(f'{OUT}/weekday_contrasts.csv', index=False); print(WK.round(3).to_string())
# DiD relocation statistic
rel = []
for m_ in ['zL', 'relRV']:
    a = np.array(bs[f'{m_}: Tuesday vs other days, Tuesday era']) - np.array(bs[f'{m_}: Tuesday vs other days, Thursday era'])
    b = np.array(bs[f'{m_}: Thursday vs other days, Tuesday era']) - np.array(bs[f'{m_}: Thursday vs other days, Thursday era'])
    ea = obs[f'{m_}: Tuesday vs other days, Tuesday era'] - obs[f'{m_}: Tuesday vs other days, Thursday era']
    eb = obs[f'{m_}: Thursday vs other days, Tuesday era'] - obs[f'{m_}: Thursday vs other days, Thursday era']
    rel.append(dict(measure=m_, tuesday_change=ea, t_lo=np.percentile(a, 2.5), t_hi=np.percentile(a, 97.5),
                    thursday_change=eb, h_lo=np.percentile(b, 2.5), h_hi=np.percentile(b, 97.5)))
REL = pd.DataFrame(rel); REL.to_csv(f'{OUT}/weekday_relocation.csv', index=False); print(REL.round(3).to_string())

# F3: weekly vs monthly by period group
wm = Epre.assign(grp=np.where(Epre.period == 'P0', 'Pre-reform', 'Post-reform')).groupby(['type', 'grp']).agg(
    n=('EVR', 'size'), EVR_med=('EVR', 'median'), L15R_med=('L15R', 'median'), alertL=('alert_L', 'mean'), absL_med=('absL', 'median')).round(3)
wm.to_csv(f'{OUT}/weekly_monthly.csv'); print(wm.to_string())

# ---------------- G. CAS descriptive (n = 9 expiries) ----------------
cas = s[s.post_cas & s.vol20.notna()]
c_rows = []
for lab, g in [('CAS expiries (n=9)', Epost), ('P3 Tuesday era', Epre[Epre.period == 'P3']), ('P0 pre-reform', Epre[Epre.period == 'P0'])]:
    c_rows.append(dict(group=lab, n=len(g), EVR_med=g.EVR.median(), EVR3_med=g.EVR3.median(), b3R_med=g.b3R.median(), EVR_mean=g.EVR.mean(),
                       EVR3_mean=g.EVR3.mean(), b3R_mean=g.b3R.mean()))
CAS = pd.DataFrame(c_rows); CAS.to_csv(f'{OUT}/cas_descriptive.csv', index=False); print(CAS.round(2).to_string())
res['cas_jump_exp_med'] = float(cas[cas.is_exp].absL.median()); res['cas_jump_non_med'] = float(cas[~cas.is_exp].absL.median())
res['cas_jump_n'] = [int(cas.is_exp.sum()), int((~cas.is_exp).sum())]
res['cas_jump_exp_list'] = [round(float(x), 1) for x in cas[cas.is_exp].absL.values]
res['cas_nonexp_jump_mean'] = float(cas[~cas.is_exp].absL.mean())
res['pre_late_nonexp_med'] = float(s[(~s.post_cas) & (~s.is_exp)].absL.median())
res['cas_single_jump_share'] = float(np.isclose((s[s.post_cas].H4 - s[s.post_cas].L4) / s[s.post_cas].O4 * 1e4, s[s.post_cas].r4.abs(), atol=0.5).mean())

# ---------------- H. Sensitivity to the matching rule ----------------
sens = []
for nm in R.SPECS:
    Ex = R.expiry_table(s, nm); Ex = Ex[Ex.period != 'P4'].copy()
    Ex['post'] = (Ex.index >= R.D1).astype(int); Ex['tue'] = (Ex.index >= R.D2).astype(int)
    for y, yn in [('lE', 'log EVR'), ('lL', 'log L15R'), ('alert_L', 'alert L15R>3')]:
        m = its(Ex, y)
        r = dict(spec=nm, outcome=yn, n=len(Ex), D1=m.params['D1'], D1_p=m.pvalues['D1'], D2=m.params['D2'], D2_p=m.pvalues['D2'], trend=m.params['t'], trend_p=m.pvalues['t'])
        for brk, bn in [(R.D1, 'lw_D1'), (R.D2, 'lw_D2')]:
            lwr = local_window(Ex, brk, y, binary=(y == 'alert_L')); r[bn] = lwr['diff']; r[bn + '_p'] = lwr['p']
        sens.append(r)
SENS = pd.DataFrame(sens); SENS.to_csv(f'{OUT}/sensitivity_matching.csv', index=False); print(SENS.round(3).to_string())

# ---------------- I. Context: was the market itself calmer/busier? ----------------
ctx = s[~s.post_cas].groupby('period').agg(sessions=('RV', 'size'), RV_med=('RV', 'median'), late_med=('absL', 'median'), cc_sd=('cc', 'std'))
ctx.to_csv(f'{OUT}/context.csv'); print(ctx.round(2).to_string())

json.dump(res, open(f'{OUT}/results.json', 'w'), indent=1, default=str)
Epre.to_pickle(f'{OUT}/Epre.pkl'); E.to_pickle(f'{OUT}/E.pkl')
print(json.dumps(res, indent=1, default=str))
