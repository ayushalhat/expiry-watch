"""RQ6 v2 additions (after review):
 A. alert-threshold robustness of the clustering tests (2x, 3x, 4x)
 B. are the direction tilt and the afternoon profile specific to expiries? same checks on placebo-day alerts
 C. stability of the structural features across eras
 D. Holm adjustment over the headline p-values
"""
import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np, pandas as pd
from scipy import stats
from statsmodels.stats.proportion import proportion_confint as pc
import rq8lib as R
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'out')
rng = np.random.default_rng(606)
B = 2000
s = R.base_sessions()
E = pd.read_pickle(f'{OUT}/E6.pkl')
res = {}

def perm_within(x, groups):
    out = x.copy()
    for g in np.unique(groups):
        idx = np.where(groups == g)[0]; out[idx] = rng.permutation(x[idx])
    return out

# ---- A: thresholds ----
rows = []
for thr in (2, 3, 4):
    a = (E.L15R > thr).astype(int).values; yrs = E.year.values
    pairs = int((a[:-1] * a[1:]).sum()); nulls = np.array([(lambda z: (z[:-1] * z[1:]).sum())(perm_within(a, yrs)) for _ in range(B)])
    prev, nxt = a[:-1], a[1:]
    p1, p0 = nxt[prev == 1].mean(), nxt[prev == 0].mean()
    rows.append(dict(threshold=f'L15R>{thr}', n_alerts=int(a.sum()), share=100 * a.mean(), adj_pairs=pairs, null_mean=float(nulls.mean()), p_adj=float((nulls >= pairs).mean()),
                     P_next_given_alert=100 * p1, P_next_given_none=100 * p0))
A = pd.DataFrame(rows); A.to_csv(f'{OUT}/v2_threshold.csv', index=False); print(A.round(2).to_string())

# ---- B: placebo-day alerts ----
sp = s[(s.index < R.D2) & s.period.notna() & (s.period != 'P4')].copy()
recs = []
for wd, nm in [(0, 'Mon'), (1, 'Tue'), (2, 'Wed'), (4, 'Fri')]:
    d = sp.copy(); d['is_exp'] = (~sp.is_exp) & (sp.index.weekday == wd)
    d = d[d.is_exp | (~sp.is_exp & (sp.index.weekday != wd))]
    mt = R.match(d, covs=('vol20',), k=3, replace=False)
    for e, cs in mt.items():
        c = d.loc[cs]; x = d.loc[e]
        r = dict(date=e, wd=nm, L15R=x.absL / max(c.absL.mean(), 1e-9), EVR=x.RV / c.RV.mean(), sign=np.sign(x.late))
        for i in (1, 2, 3): r[f'b{i}R'] = x[f'abs{i}'] / max(c[f'abs{i}'].mean(), 1e-9)
        recs.append(r)
PL = pd.DataFrame(recs).set_index('date').sort_index()
PL['alert'] = (PL.L15R > 3).astype(int)
EX = E[E.index < R.D2]
pa = PL[PL.alert == 1]; ea = EX[EX.alert_L == 1]
up_p = float((pa.sign > 0).mean()); up_e = float((ea.sign > 0).mean())
tab = [[int((ea.sign > 0).sum()), int((ea.sign < 0).sum())], [int((pa.sign > 0).sum()), int((pa.sign < 0).sum())]]
res['direction'] = dict(expiry_alert_up=int((ea.sign > 0).sum()), expiry_alert_n=int((ea.sign != 0).sum()), placebo_alert_up=int((pa.sign > 0).sum()), placebo_alert_n=int((pa.sign != 0).sum()),
                        expiry_up_share=100 * up_e, placebo_up_share=100 * up_p, fisher_p=float(stats.fisher_exact(tab)[1]))
def runs(x): return 1 + int((x[1:] != x[:-1]).sum())
sg = pa.sign.values; sg = sg[sg != 0]; o = runs(sg); nl = np.array([runs(rng.permutation(sg)) for _ in range(B)])
res['placebo_runs'] = dict(n=len(sg), runs=o, null_mean=float(nl.mean()), p=float(min(1, 2 * min((nl <= o).mean(), (nl >= o).mean()))))
prof = pd.DataFrame([dict(group='Expiry alerts (L15R>3), Thursday era', n=len(ea), b1R=ea.b1R.median(), b2R=ea.b2R.median(), b3R=ea.b3R.median()),
                     dict(group='Placebo-day alerts (L15R>3)', n=len(pa), b1R=pa.b1R.median(), b2R=pa.b2R.median(), b3R=pa.b3R.median()),
                     dict(group='Expiries without alert', n=int((EX.alert_L == 0).sum()), b1R=EX[EX.alert_L == 0].b1R.median(), b2R=EX[EX.alert_L == 0].b2R.median(), b3R=EX[EX.alert_L == 0].b3R.median()),
                     dict(group='Placebo days without alert', n=int((PL.alert == 0).sum()), b1R=PL[PL.alert == 0].b1R.median(), b2R=PL[PL.alert == 0].b2R.median(), b3R=PL[PL.alert == 0].b3R.median())])
prof.to_csv(f'{OUT}/v2_profile_placebo.csv', index=False); print(prof.round(2).to_string()); print(res)
# is the afternoon profile expiry-specific? bar-3 ratio expiry-alert vs placebo-alert
res['b3_mw_p_expiry_vs_placebo_alerts'] = float(stats.mannwhitneyu(ea.b3R, pa.b3R).pvalue)

# ---- C: era stability ----
rows = []
for nm, g in [('2019-2022', E[E.index < '2023-01-01']), ('2023-2026', E[E.index >= '2023-01-01'])]:
    w, m = g[g.type == 'weekly'], g[g.type == 'monthly']
    tab = [[int(m.alert_L.sum()), len(m) - int(m.alert_L.sum())], [int(w.alert_L.sum()), len(w) - int(w.alert_L.sum())]]
    pg = PL[(PL.index >= g.index.min()) & (PL.index <= min(g.index.max(), R.D2 - pd.Timedelta(days=1)))]
    eg = g[g.index < R.D2]
    rows.append(dict(era=nm, n=len(g), alertL=100 * g.alert_L.mean(), weekly_n=len(w), weekly=100 * w.alert_L.mean(), monthly_n=len(m), monthly=100 * m.alert_L.mean(),
                     monthly_vs_weekly_fisher_p=float(stats.fisher_exact(tab)[1]), thursday_expiry=100 * eg.alert_L.mean(), placebo=100 * pg.alert.mean(), placebo_n=len(pg)))
C = pd.DataFrame(rows); C.to_csv(f'{OUT}/v2_era.csv', index=False); print(C.round(2).to_string())

# ---- D: Holm over headline p-values ----
T1 = pd.read_csv(f'{OUT}/T1_serial.csv'); T1 = T1[(T1.spec == 'primary (no replacement)') & T1.outcome.isin(['log L15R', 'log EVR'])]
T2 = pd.read_csv(f'{OUT}/T2_clustering.csv'); T2 = T2[T2.spec == 'primary (no replacement)']
T3 = pd.read_csv(f'{OUT}/T3_regime_concentration.csv'); T4 = pd.read_csv(f'{OUT}/T4_signature.csv'); r6 = json.load(open(f'{OUT}/results.json')); ex = json.load(open(f'{OUT}/extra.json'))
heads = [('T1 serial dependence, smallest of 8 autocorrelations', float(T1.p_full.min())),
         ('T2 clustering, L15R adjacent pairs', float(T2.p_adj.iloc[0])),
         ('T3 regime concentration, L15R', float(T3.p.iloc[0])),
         ('T4 bar-pattern similarity, L15R alerts', float(T4.p.iloc[0])),
         ('T5 runs of direction among L15R alerts', float(r6['T5_runs']['p_two'])),
         ('S1 monthly vs weekly alert rate (Fisher)', float(ex['fisher_monthly_vs_weekly_alertL']['p'])),
         ('S2 expiry vs placebo-day alert rate (Fisher)', 0.0017292000152934776),
         ('S3 up-share of alerts vs other expiries (binomial)', float(ex['direction']['binom_p_vs_nonalert']))]
p = np.array([h[1] for h in heads]); o = np.argsort(p); m = len(p); adj = np.empty(m); run = 0
for rk, i in enumerate(o): run = max(run, (m - rk) * p[i]); adj[i] = min(1, run)
D = pd.DataFrame(dict(test=[h[0] for h in heads], p=p, p_holm=adj)); D.to_csv(f'{OUT}/v2_holm.csv', index=False); print(D.round(4).to_string())
json.dump(res, open(f'{OUT}/v2.json', 'w'), indent=1, default=str)
