"""RQ6 secondary checks (added after seeing the main results): baseline alert rates on placebo weekdays, weekly vs monthly, direction imbalance."""
import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np, pandas as pd
import statsmodels.api as sm
from scipy.stats import fisher_exact, binomtest
import rq8lib as R
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'out')
rng = np.random.default_rng(66)
s = R.base_sessions()
E = pd.read_pickle(f'{OUT}/E6.pkl'); res = {}
# --- weekly vs monthly, quarter end
tab = pd.crosstab(E.type, E.alert_L); print(tab)
res['fisher_monthly_vs_weekly_alertL'] = dict(p=float(fisher_exact(tab.values)[1]), monthly=float(E[E.type == 'monthly'].alert_L.mean()), weekly=float(E[E.type == 'weekly'].alert_L.mean()))
X = pd.DataFrame({'c': 1.0, 'monthly': (E.type == 'monthly').astype(float), 'qend': E.quarter_end.astype(float), 't': E.t}, index=E.index)
m = sm.Logit(E.alert_L, X).fit(disp=0, cov_type='HC1'); print(m.summary2().tables[1].round(3))
res['logit_alertL'] = {k: dict(coef=float(m.params[k]), p=float(m.pvalues[k]), lo=float(m.conf_int().loc[k, 0]), hi=float(m.conf_int().loc[k, 1])) for k in X.columns}
m2 = sm.OLS(E.lL, X).fit(cov_type='HAC', cov_kwds={'maxlags': 4}); print(m2.summary2().tables[1].round(3))
res['ols_lL'] = {k: dict(coef=float(m2.params[k]), p=float(m2.pvalues[k]), lo=float(m2.conf_int().loc[k, 0]), hi=float(m2.conf_int().loc[k, 1])) for k in X.columns}
# --- direction
a = E[E.alert_L == 1]; up = int((a.sign > 0).sum()); n = int((a.sign != 0).sum())
base_up = float((E.sign > 0).mean()); nonalert_up = float((E[E.alert_L == 0].sign > 0).mean())
res['direction'] = dict(alert_up=up, alert_n=n, binom_p_vs_half=float(binomtest(up, n, 0.5).pvalue), all_expiry_up_share=base_up, nonalert_up_share=nonalert_up,
                        binom_p_vs_nonalert=float(binomtest(up, n, nonalert_up).pvalue))
# --- placebo weekdays (Thursday era only): same alert definitions, same no-replacement rule
sp = s[(s.index < R.D2) & s.period.notna() & (s.period != 'P4')].copy()
rows = []
ex = E[E.index < R.D2]
rows.append(dict(group='Thursday expiries', n=len(ex), alertL=100 * ex.alert_L.mean(), alertE=100 * ex.alert_E.mean(), L15R_med=ex.L15R.median(), EVR_med=ex.EVR.median()))
nonexp = sp[~sp.is_exp]
for wd, nm in [(0, 'Monday'), (1, 'Tuesday'), (2, 'Wednesday'), (4, 'Friday')]:
    d = sp.copy(); d['is_exp'] = (~sp.is_exp) & (sp.index.weekday == wd)
    d = d[d.is_exp | (~sp.is_exp & (sp.index.weekday != wd))]
    mt = R.match(d, covs=('vol20',), k=3, replace=False)
    r = []
    for e, cs in mt.items():
        c = d.loc[cs]; x = d.loc[e]
        r.append(dict(L15R=x.absL / max(c.absL.mean(), 1e-9), EVR=x.RV / c.RV.mean()))
    r = pd.DataFrame(r)
    rows.append(dict(group=f'{nm} (placebo)', n=len(r), alertL=100 * (r.L15R > 3).mean(), alertE=100 * (r.EVR > 2.7).mean(), L15R_med=r.L15R.median(), EVR_med=r.EVR.median()))
PL = pd.DataFrame(rows); PL.to_csv(f'{OUT}/S_placebo_alert_rates.csv', index=False); print(PL.round(2).to_string())
json.dump(res, open(f'{OUT}/extra.json', 'w'), indent=1, default=str); print(json.dumps(res, indent=1, default=str))
