import json, sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np, pandas as pd
import statsmodels.api as sm
from scipy import stats
import rq8lib as R
import rq5lib as L

OUT = sys.argv[1]
rng = np.random.default_rng(99)
s = R.base_sessions()
E = pd.read_pickle(f'{OUT}/E.pkl'); Epre = pd.read_pickle(f'{OUT}/Epre.pkl')
res = {}
Epre = Epre.copy()
for i in (1, 2, 3):
    Epre[f'lb{i}'] = np.log(Epre[f'b{i}R'].clip(lower=0.02))

def fit(df, y, extra=None, brk=None, maxlags=4):
    X = pd.DataFrame({'const': 1.0, 't': df.t.values}, index=df.index)
    for nm, d0 in (brk or [('D1', R.D1), ('D2', R.D2)]):
        X[nm] = (df.index >= d0).astype(float)
    return sm.OLS(df[y], X).fit(cov_type='HAC', cov_kwds={'maxlags': maxlags})

# 1. trend-adjusted ITS for the other bars (relocation to earlier in the day?) and last bar
rows = []
for y, nm in [('lb1', 'bar 09:15-11:15'), ('lb2', 'bar 11:15-13:15'), ('lb3', 'bar 13:15-15:15'), ('lL', 'bar 15:15-15:30 (L15R)')]:
    m = fit(Epre, y)
    for term in ['t', 'D1', 'D2']:
        rows.append(dict(outcome=nm, term=term, coef=m.params[term], se=m.bse[term], p=m.pvalues[term], lo=m.params[term] - 1.96 * m.bse[term], hi=m.params[term] + 1.96 * m.bse[term]))
B = pd.DataFrame(rows); B.to_csv(f'{OUT}/its_bars.csv', index=False); print(B.round(3).to_string())

# 2. weekly / monthly ITS (levels spec) from main file
its = pd.read_csv(f'{OUT}/its.csv')
x = its[(its.spec == 'levels') & (its.term.isin(['t', 'D1', 'D2'])) & (its['sample'] != 'all expiries')]
print(x[['sample', 'outcome', 'term', 'coef', 'se', 'p']].round(3).to_string())

# 3. scan incl. EVR alert, plus null calibration of the ITS level shift with fake break dates in the pre-reform sample
w = 26
scan = []
for i in range(w, len(Epre) - w + 1):
    a = Epre.iloc[i - w:i]; b = Epre.iloc[i:i + w]
    scan.append(dict(date=Epre.index[i], dAE=100 * (b.alert_E.mean() - a.alert_E.mean())))
SC = pd.DataFrame(scan).set_index('date')
row = SC[SC.index >= R.D1].iloc[0]
res['scan_D1_alertE'] = dict(value=float(row.dAE), share_as_extreme=float((SC.dAE.abs() >= abs(row.dAE)).mean()), n=int(len(SC)), min_dAE=float(SC.dAE.min()), date=str(row.name.date()))
row2 = SC[SC.index >= R.D2].iloc[0]
res['scan_D2_alertE'] = dict(value=float(row2.dAE), share_as_extreme=float((SC.dAE.abs() >= abs(row2.dAE)).mean()))

P0 = Epre[Epre.index < R.D1]
fake = []
idx = range(60, len(P0) - 40, 10)
for i in idx:
    b = P0.index[i]
    X = pd.DataFrame({'const': 1.0, 't': P0.t.values, 'F': (P0.index >= b).astype(float)}, index=P0.index)
    r = dict(date=b)
    for y in ['lE', 'lL', 'alert_E', 'alert_L']:
        m = sm.OLS(P0[y], X).fit(cov_type='HAC', cov_kwds={'maxlags': 4}); r[y] = m.params['F']
    fake.append(r)
FK = pd.DataFrame(fake).set_index('date'); FK.to_csv(f'{OUT}/fake_break_levels.csv')
main = {}
for y in ['lE', 'lL', 'alert_E', 'alert_L']:
    m = fit(Epre, y); main[y] = m.params['D1']
    res[f'fake_{y}'] = dict(actual_D1=float(main[y]), n_fake=int(len(FK)), sd_fake=float(FK[y].std()), share_fake_as_extreme=float((FK[y].abs() >= abs(main[y])).mean()),
                            fake_min=float(FK[y].min()), fake_max=float(FK[y].max()))
print({k: v for k, v in res.items() if k.startswith(('fake', 'scan'))})

# 4. alternative break dates for the phased reforms
alt = []
for nm, d1 in [('2024-10-01 package announced + STT (primary)', pd.Timestamp('2024-10-01')), ('2024-11-20 phase 1 effective', pd.Timestamp('2024-11-20')),
               ('2025-02-01 phase 2', pd.Timestamp('2025-02-01')), ('2025-04-01 phase 3 complete', pd.Timestamp('2025-04-01'))]:
    for y, yn in [('lE', 'log EVR'), ('lL', 'log L15R'), ('alert_E', 'alert EVR>2.7'), ('alert_L', 'alert L15R>3')]:
        m = fit(Epre, y, brk=[('D1', d1), ('D2', R.D2)])
        alt.append(dict(D1_date=nm, outcome=yn, D1=m.params['D1'], se=m.bse['D1'], p=m.pvalues['D1'], D2=m.params['D2'], D2_p=m.pvalues['D2']))
AL = pd.DataFrame(alt); AL.to_csv(f'{OUT}/its_alt_break_dates.csv', index=False); print(AL.round(3).to_string())

# 5. shorter pre-period (from 2022) to test the linear-trend assumption
sh = Epre[Epre.index >= '2022-01-01']
rows = []
for y, yn in [('lE', 'log EVR'), ('lL', 'log L15R'), ('alert_E', 'alert EVR>2.7'), ('alert_L', 'alert L15R>3')]:
    m = fit(sh, y)
    rows.append(dict(outcome=yn, n=len(sh), trend=m.params['t'], D1=m.params['D1'], D1_se=m.bse['D1'], D1_p=m.pvalues['D1'], D2=m.params['D2'], D2_p=m.pvalues['D2']))
SH = pd.DataFrame(rows); SH.to_csv(f'{OUT}/its_from2022.csv', index=False); print(SH.round(3).to_string())

# 6. matching-rule sensitivity for the EVR>2.7 alert and log EVR D1
sens = []
for nm in R.SPECS:
    Ex = R.expiry_table(s, nm); Ex = Ex[Ex.period != 'P4']
    for y in ['alert_E', 'lE']:
        m = fit(Ex, y)
        sens.append(dict(spec=nm, outcome=y, D1=m.params['D1'], p=m.pvalues['D1'], D2=m.params['D2'], D2_p=m.pvalues['D2']))
SE_ = pd.DataFrame(sens); SE_.to_csv(f'{OUT}/sensitivity_evr_alert.csv', index=False); print(SE_.round(3).to_string())

# 7. what are the alert expiries after the reforms?
ev = pd.read_excel(L.XLSX, sheet_name='Events'); ev['Date'] = pd.to_datetime(ev['Date'], errors='coerce'); ev = ev.dropna(subset=['Date'])
post = Epre[Epre.index >= R.D1]
al = post[(post.alert_L == 1) | (post.alert_E == 1)][['type', 'regime', 'EVR', 'L15R', 'absL', 'alert_L', 'alert_E']].copy()
al['event_overlap'] = [bool((ev.Date == d).any()) for d in al.index]
al.round(2).to_csv(f'{OUT}/post_reform_alerts.csv'); print(al.round(2).to_string())
pre_al = Epre[(Epre.index < R.D1) & (Epre.alert_E == 1)]
print('EVR>2.7 expiries before D1:', len(pre_al), '| by year:', pre_al.groupby(pre_al.index.year).size().to_dict(), '| share with event overlap:',
      float(np.mean([bool((ev.Date == d).any()) for d in pre_al.index])))
res['pre_alertE_by_year'] = {int(k): int(v) for k, v in pre_al.groupby(pre_al.index.year).size().items()}
res['alertE_by_year_all'] = {int(k): [int(v.alert_E.sum()), int(len(v))] for k, v in Epre.groupby(Epre.index.year)}
res['alertL_by_year_all'] = {int(k): [int(v.alert_L.sum()), int(len(v))] for k, v in Epre.groupby(Epre.index.year)}

# 8. power: smallest effects the ITS could detect (80% power, 5% two-sided = 2.8 x SE)
for y, nm in [('lE', 'log EVR'), ('lL', 'log L15R'), ('alert_L', 'alert L15R>3'), ('alert_E', 'alert EVR>2.7')]:
    m = fit(Epre, y)
    res[f'mde_{y}'] = dict(D1=float(2.8 * m.bse['D1']), D2=float(2.8 * m.bse['D2']))
print({k: v for k, v in res.items() if k.startswith('mde')})
json.dump(res, open(f'{OUT}/extra.json', 'w'), indent=1, default=str)
