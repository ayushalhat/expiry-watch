"""RQ6 (expiry half): do similar anomaly signatures recur across expiries?
PRE-SPECIFIED PLAN (written before any RQ6 outcome was computed)
Scope: NIFTY only. The 'across indices' half cannot be tested (no other index in the data).
Sample: pre-CAS expiries with 3 matched controls (367). CAS expiries excluded (last bar not comparable).
Primary outcome series: lL = log((|last-bar move|+.5)/(matched-control mean+.5)) and lE = log EVR, using the matching rule WITHOUT
  replacement (vol20 only) so that adjacent expiries never share controls (shared controls would create artificial positive serial correlation).
Sensitivity: primary RQ8 rule (with replacement), zL (own trailing scale, biased negative), absL/vol20.
Tests (each with permutation null, 5000 draws, seed 6):
 T1 serial dependence: lag-1..4 autocorrelation of residuals from OLS on [1,t,D1,D2]; null (a) full shuffle of residuals, (b) shuffle within calendar year.
 T2 clustering of alerts (L15R>3, EVR>2.7): adjacent-pair count and 'alerts within a 4-expiry window' count; null within calendar year.
 T3 concentration of alerts across the 12 pre-CAS regimes (sum of squared shares), null: shuffle labels over all expiries.
 T4 signature similarity: mean pairwise cosine similarity of the centred per-bar log-ratio vector (bars 1-3) among L15R-alert expiries vs random expiry sets of the same size.
 T5 direction recurrence: runs test on the sign of the late move among L15R-alert expiries (time order) and sign persistence after a large late move.
 T6 events: share of alerts on Events-sheet dates vs share of all expiries.
Secondary (not primary): everything beyond T1-T6.
"""
import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np, pandas as pd
import statsmodels.api as sm
import rq8lib as R
rng = np.random.default_rng(6)
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'out')
B = 5000
s = R.base_sessions()
res = {}

def table(spec):
    E = R.expiry_table(s, spec); E = E[E.period != 'P4'].copy()
    E['year'] = E.index.year
    E['sign'] = np.sign(s.loc[E.index, 'late'].values)
    E['y_zL'] = np.log(E.zL + 0.1)
    E['y_rel'] = np.log((E.absL + 0.5) / E.vol20)
    return E

SPEC_P = 'vol20 only, no replacement'
E = table(SPEC_P); E_rep = table('primary: vol20+vol5')
res['n'] = len(E)

def resid(E, y):
    X = pd.DataFrame({'c': 1.0, 't': E.t.values, 'D1': (E.index >= R.D1).astype(float), 'D2': (E.index >= R.D2).astype(float)}, index=E.index)
    return sm.OLS(E[y].values, X.values).fit().resid

def acf(x, k):
    x = x - x.mean(); return float((x[:-k] * x[k:]).sum() / (x * x).sum())

def perm_within(x, groups, rs):
    out = x.copy()
    for g in np.unique(groups):
        idx = np.where(groups == g)[0]; out[idx] = rs.permutation(x[idx])
    return out

# ---------- T1 ----------
rows = []
for spec_name, EE in [('primary (no replacement)', E), ('sensitivity: with replacement', E_rep)]:
    for y, yn in [('lL', 'log L15R'), ('lE', 'log EVR'), ('y_zL', 'log zL (own scale)'), ('y_rel', 'log |last bar|/vol20')]:
        r = resid(EE, y); yrs = EE.year.values
        for k in range(1, 5):
            obs = acf(r, k)
            nf = np.array([acf(rng.permutation(r), k) for _ in range(B)])
            nw = np.array([acf(perm_within(r, yrs, rng), k) for _ in range(B)])
            rows.append(dict(spec=spec_name, outcome=yn, lag=k, acf=obs, p_full=float((np.abs(nf) >= abs(obs)).mean()), p_withinyear=float((np.abs(nw) >= abs(obs)).mean()),
                             null_sd=float(nf.std())))
T1 = pd.DataFrame(rows); T1.to_csv(f'{OUT}/T1_serial.csv', index=False); print(T1.round(3).to_string())

# ---------- T2 ----------
def adj_pairs(a): return int((a[:-1] * a[1:]).sum())
def win_count(a, w=4):
    c = np.convolve(a, np.ones(w), 'valid'); return int((c >= 2).sum())
rows = []
for col, nm in [('alert_L', 'L15R>3'), ('alert_E', 'EVR>2.7')]:
    for spec_name, EE in [('primary (no replacement)', E), ('sensitivity: with replacement', E_rep)]:
        a = EE[col].values.astype(int); yrs = EE.year.values
        o1, o2 = adj_pairs(a), win_count(a)
        n1 = np.array([adj_pairs(perm_within(a, yrs, rng)) for _ in range(B)]); n2 = np.array([win_count(perm_within(a, yrs, rng)) for _ in range(B)])
        rows.append(dict(alert=nm, spec=spec_name, n_alerts=int(a.sum()), adj_pairs=o1, adj_pairs_null_mean=float(n1.mean()), p_adj=float((n1 >= o1).mean()),
                         win4=o2, win4_null_mean=float(n2.mean()), p_win=float((n2 >= o2).mean())))
T2 = pd.DataFrame(rows); T2.to_csv(f'{OUT}/T2_clustering.csv', index=False); print(T2.round(3).to_string())
# conditional probability of an alert after an alert
rows = []
for col, nm in [('alert_L', 'L15R>3'), ('alert_E', 'EVR>2.7')]:
    a = E[col].values.astype(int); prev = a[:-1]; nxt = a[1:]
    rows.append(dict(alert=nm, P_next_given_alert=float(nxt[prev == 1].mean()), n_prev_alert=int(prev.sum()), P_next_given_none=float(nxt[prev == 0].mean()), base=float(a.mean())))
T2b = pd.DataFrame(rows); T2b.to_csv(f'{OUT}/T2_conditional.csv', index=False); print(T2b.round(3).to_string())

# ---------- T3 ----------
rows = []
for col, nm in [('alert_L', 'L15R>3'), ('alert_E', 'EVR>2.7')]:
    a = E[col].values.astype(int); rg = E.regime.values; regs = np.unique(rg)
    def stat(a):
        c = np.array([a[rg == r].sum() for r in regs], float); return float(((c / c.sum()) ** 2).sum())
    obs = stat(a); nl = np.array([stat(rng.permutation(a)) for _ in range(B)])
    rows.append(dict(alert=nm, stat=obs, null_mean=float(nl.mean()), p=float((nl >= obs).mean()), top_regime=str(pd.Series(a, index=rg).groupby(level=0).sum().idxmax()),
                     top_regime_alerts=int(pd.Series(a, index=rg).groupby(level=0).sum().max()), n_alerts=int(a.sum())))
T3 = pd.DataFrame(rows); T3.to_csv(f'{OUT}/T3_regime_concentration.csv', index=False); print(T3.round(3).to_string())
rt = E.groupby('regime').agg(n=('alert_L', 'size'), alertL=('alert_L', 'sum'), alertE=('alert_E', 'sum')); rt.to_csv(f'{OUT}/T3_by_regime.csv'); print(rt.to_string())

# ---------- T4 ----------
V = np.log(E[['b1R', 'b2R', 'b3R']].clip(lower=0.05)).values
V = V - V.mean(axis=0)
def meancos(idx):
    X = V[idx]; nrm = np.linalg.norm(X, axis=1, keepdims=True); X = X / np.where(nrm == 0, 1, nrm); C = X @ X.T
    k = len(idx); return float((C.sum() - np.trace(C)) / (k * (k - 1)))
rows = []
for col, nm in [('alert_L', 'L15R>3'), ('alert_E', 'EVR>2.7')]:
    idx = np.where(E[col].values == 1)[0]; obs = meancos(idx)
    nl = np.array([meancos(rng.choice(len(E), len(idx), replace=False)) for _ in range(B)])
    rows.append(dict(alert=nm, k=len(idx), mean_cos=obs, null_mean=float(nl.mean()), null_sd=float(nl.std()), p=float((nl >= obs).mean())))
T4 = pd.DataFrame(rows); T4.to_csv(f'{OUT}/T4_signature.csv', index=False); print(T4.round(3).to_string())
# what the anomaly day looks like in the other bars
al = E[E.alert_L == 1]; na = E[E.alert_L == 0]
rows = [dict(group='L15R>3 expiries', n=len(al), b1R=al.b1R.median(), b2R=al.b2R.median(), b3R=al.b3R.median(), EVR3=al.EVR3.median(), EVR=al.EVR.median()),
        dict(group='other expiries', n=len(na), b1R=na.b1R.median(), b2R=na.b2R.median(), b3R=na.b3R.median(), EVR3=na.EVR3.median(), EVR=na.EVR.median())]
T4b = pd.DataFrame(rows); T4b.to_csv(f'{OUT}/T4_day_profile.csv', index=False); print(T4b.round(2).to_string())
from scipy.stats import mannwhitneyu
res['T4_evr3_mw_p'] = float(mannwhitneyu(al.EVR3, na.EVR3).pvalue)

# ---------- T5 ----------
a = E[E.alert_L == 1]; sg = a.sign.values; sg = sg[sg != 0]
def nruns(x): return 1 + int((x[1:] != x[:-1]).sum())
obs = nruns(sg); nl = np.array([nruns(rng.permutation(sg)) for _ in range(B)])
res['T5_runs'] = dict(n=len(sg), up=int((sg > 0).sum()), down=int((sg < 0).sum()), runs=obs, null_mean=float(nl.mean()), p_two=float(min(1, 2 * min((nl <= obs).mean(), (nl >= obs).mean()))))
# sign persistence: after an alert expiry, is the next alert expiry's late move the same direction?
# general: correlation of signed late move (normalised) across consecutive expiries
sl = (s.loc[E.index, 'late'] / s.loc[E.index, 'scale']).replace([np.inf, -np.inf], np.nan).dropna()
x = np.sign(sl.values); res['T5_sign_agree_consecutive'] = float((x[1:] == x[:-1]).mean())
nl = np.array([(lambda z: (z[1:] == z[:-1]).mean())(rng.permutation(x)) for _ in range(B)])
res['T5_sign_agree_null'] = float(nl.mean()); res['T5_sign_agree_p'] = float((np.abs(nl - nl.mean()) >= abs(res['T5_sign_agree_consecutive'] - nl.mean())).mean())

# ---------- T6 ----------
ev = pd.read_excel('/mnt/user-data/attachments/843f0391-b502-5c5c-83b5-b028439046ef/f186ebdc-Database.xlsx', sheet_name='Events')
ev['Date'] = pd.to_datetime(ev['Date'], errors='coerce'); ev = ev.dropna(subset=['Date'])
evd = set(ev.Date.dt.normalize()); ison = E.index.isin(list(evd))
res['T6'] = dict(n_events_on_expiry=int(ison.sum()), share_all=float(ison.mean()), alert_L_on_event=int(E.alert_L[ison].sum()), alert_E_on_event=int(E.alert_E[ison].sum()),
                 alert_L_total=int(E.alert_L.sum()), alert_E_total=int(E.alert_E.sum()), event_dates=[str(d.date()) for d in E.index[ison]])
print(res['T6'])

# ---------- Secondary: episodes, recurrence by expiry type / quarter end ----------
w = E.alert_L.values; rows = []
c = np.convolve(w, np.ones(4), 'valid'); ep = np.where(c >= 2)[0]
eps = []
for i in ep:
    if eps and i <= eps[-1][1] + 1: eps[-1][1] = i + 3
    else: eps.append([i, i + 3])
EP = pd.DataFrame([dict(start=E.index[a_].date(), end=E.index[min(b_, len(E) - 1)].date(), n_alerts=int(w[a_:b_ + 1].sum()), n_expiries=int(min(b_, len(E) - 1) - a_ + 1)) for a_, b_ in eps])
EP.to_csv(f'{OUT}/S_episodes_L15R.csv', index=False); print(EP.to_string())
res['episodes_n'] = len(EP); res['episodes_alerts_share'] = float(EP.n_alerts.sum() / w.sum()) if len(EP) else 0
rows = []
for nm, g in [('weekly', E[E.type == 'weekly']), ('monthly', E[E.type == 'monthly']), ('quarter-end', E[E.quarter_end]), ('not quarter-end', E[~E.quarter_end])]:
    rows.append(dict(group=nm, n=len(g), alertL=100 * g.alert_L.mean(), alertE=100 * g.alert_E.mean(), L15R_med=g.L15R.median(), EVR_med=g.EVR.median()))
S = pd.DataFrame(rows); S.to_csv(f'{OUT}/S_type.csv', index=False); print(S.round(2).to_string())
E.to_pickle(f'{OUT}/E6.pkl')
json.dump(res, open(f'{OUT}/results.json', 'w'), indent=1, default=str); print(json.dumps(res, indent=1, default=str))
