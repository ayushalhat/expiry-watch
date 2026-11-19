"""RQ8 library: reform periods, matched controls, expiry-level outcome table.

PRE-SPECIFIED PLAN (written before any RQ8 outcome was computed)
----------------------------------------------------------------
Question: did the 2024-26 derivatives and closing-price reforms reduce or relocate expiry-day anomalies?
Reform breaks (first expiry governed by the rule, from the Regimes / Settlement sheets):
  D1 = 2024-10-01  SEBI Oct-2024 framework + STT hike; phased in 2024-11-20 (R06), 2025-02-01 (R08), 2025-04-01 (R09)
  D2 = 2025-09-01  expiry moves Thu -> Tue, intraday position-limit monitoring
  CAS = 2026-08-03 closing auction session (descriptive only, 9 expiries)
Periods: P0 pre-reform (to 2024-09-30), P1 phase-in (2024-10-01..2025-03-31), P2 (2025-04-01..2025-08-31),
         P3 Tuesday era (2025-09-01..2026-08-02), P4 CAS (from 2026-08-03).
Outcomes (expiry vs 3 matched controls, as in RQ1/RQ2): EVR (whole-day), L15R (last-15-min |move| ratio),
  extreme-alert rates: L15R > 3 and EVR > 2.7 (the RQ1 report's thresholds).
PRIMARY tests: (i) interrupted time series on log L15R and log EVR: linear pre-trend + level shifts at D1 and D2
  (slopes held constant; slope changes = sensitivity), HAC s.e.; (ii) local-window comparison, 26 expiries either side of each break;
  (iii) the same two for the alert indicator L15R > 3.
Relocation: per-bar ratios, weekday profile Thursday era vs Tuesday era, weekly vs monthly.
Null calibration: scan of all other break dates (same local-window statistic).
Primary matching rule: Mahalanobis on log(vol20, vol5), k = 3, with replacement, within regime (best tie-out to the
  sheet's Mean_EVR); sensitivity: default RQ5 rule, vol5+range5, vol20 only without replacement.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
import pandas as pd
import rq5lib as L

D1 = pd.Timestamp('2024-10-01')
D2 = pd.Timestamp('2025-09-01')
CAS = L.CAS_START
T0 = pd.Timestamp('2019-06-26')
PERIODS = [('P0', '2019-06-26', '2024-09-30'), ('P1', '2024-10-01', '2025-03-31'), ('P2', '2025-04-01', '2025-08-31'),
           ('P3', '2025-09-01', '2026-08-02'), ('P4', '2026-08-03', '2100-01-01')]
SPECS = {
    'primary: vol20+vol5': dict(covs=('vol20', 'vol5')),
    'RQ5 rule: vol20+vol5+|prev day|': dict(covs=('vol20', 'vol5', 'prev_abs')),
    'vol5+range5': dict(covs=('vol5', 'range5')),
    'vol20 only, no replacement': dict(covs=('vol20',), replace=False),
}


def period_of(d):
    for name, a, b in PERIODS:
        if pd.Timestamp(a) <= d <= pd.Timestamp(b):
            return name
    return None


def match(s, covs, k=3, replace=True):
    d = s.copy()
    X = np.log(d[list(covs)].clip(lower=1e-3))
    ok = X.notna().all(axis=1) & d.regime.notna()
    d, X = d[ok], X[ok]
    cinv = np.linalg.pinv(np.atleast_2d(np.cov(X.values.T)))
    out = {}
    for rg, grp in d.groupby('regime'):
        ex = grp[grp.is_exp]; ct = grp[~grp.is_exp]
        if len(ct) < k or len(ex) == 0:
            continue
        Xc = X.loc[ct.index].values
        used = set()
        for e in ex.index:
            diff = Xc - X.loc[e].values
            dd = np.einsum('ij,jk,ik->i', diff, cinv, diff)
            order = [i for i in np.argsort(dd) if (replace or i not in used)][:k]
            used.update(order)
            out[e] = list(ct.index[order])
    return out


def base_sessions():
    s = L.build_all()
    for i in range(1, 5):
        s[f'abs{i}'] = s[f'r{i}'].abs()
    s['RV3'] = np.sqrt((s[['r1', 'r2', 'r3']] ** 2).sum(axis=1))
    s['rvtr'] = s.RV.shift(1).rolling(20).mean()
    s['relRV'] = s.RV / s.rvtr
    s['zL'] = s.absL / s.scale
    s['period'] = [period_of(d) for d in s.index]
    return s


def expiry_table(s, spec_name='primary: vol20+vol5'):
    m = match(s, **SPECS[spec_name])
    rows = []
    for e, cs in m.items():
        c = s.loc[cs]; x = s.loc[e]
        row = dict(date=e, type=x.exp_type, weekday=e.weekday(), regime=x.regime, period=x.period, quarter_end=bool(x.quarter_end),
                   t=(e - T0).days / 365.25, absL=x.absL, RV=x.RV, RV3=x.RV3, zL=x.zL,
                   EVR=x.RV / c.RV.mean(), EVR3=x.RV3 / c.RV3.mean(), L15R=x.absL / max(c.absL.mean(), 1e-9),
                   ctrl_absL=c.absL.mean(), vol20=x.vol20)
        for i in range(1, 5):
            row[f'b{i}R'] = x[f'abs{i}'] / max(c[f'abs{i}'].mean(), 1e-9)
        rows.append(row)
    E = pd.DataFrame(rows).set_index('date').sort_index()
    E['lL'] = np.log((E.absL + 0.5) / (E.ctrl_absL + 0.5))
    E['lE'] = np.log(E.EVR)
    E['alert_L'] = (E.L15R > 3).astype(int)
    E['alert_E'] = (E.EVR > 2.7).astype(int)
    E['alert_z'] = (E.zL >= 3).astype(int)
    return E
