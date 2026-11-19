"""Calibrate the rebuilt matched-control rule against the Mean_EVR column of the Regimes sheet."""
import sys, os, itertools
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np, pandas as pd
import rq5lib as L

s = L.build_all()
reg = L.load_regimes()
sheet = pd.read_excel(L.XLSX, sheet_name='Regimes', header=0).iloc[:14]
sheet = sheet[sheet['Regime ID'].astype(str).str.startswith('R')].set_index('Regime ID')['Mean_EVR'].astype(float)

def match(s, covs, k=3, dist='maha', replace=True, loglev=True, pre_cas_only=False, restrict=None):
    d = s.copy()
    X = d[list(covs)].clip(lower=1e-3)
    if loglev: X = np.log(X)
    ok = X.notna().all(axis=1) & d.regime.notna()
    d, X = d[ok], X[ok]
    if dist == 'maha':
        cinv = np.linalg.pinv(np.atleast_2d(np.cov(X.values.T)))
    else:
        sd = X.std().values; cinv = np.diag(1 / sd ** 2)
    out = {}
    for rg, grp in d.groupby('regime'):
        ex = grp[grp.is_exp]; ct = grp[~grp.is_exp]
        if restrict is not None: ct = ct[restrict(ct)]
        if len(ct) < k or len(ex) == 0: continue
        Xc = X.loc[ct.index].values; used = set()
        for e in ex.index:
            diff = Xc - X.loc[e].values
            dd = np.einsum('ij,jk,ik->i', diff, cinv, diff)
            order = np.argsort(dd)
            if not replace:
                order = [i for i in order if i not in used][:k]; used.update(order)
            else:
                order = order[:k]
            out[e] = list(ct.index[order])
    return out

def evr_by_regime(m):
    rows = []
    for e, cs in m.items():
        rows.append(dict(regime=s.loc[e, 'regime'], EVR=s.loc[e, 'RV'] / s.loc[cs, 'RV'].mean()))
    r = pd.DataFrame(rows)
    return r.groupby('regime').EVR.mean()

specs = {
    'maha vol20,vol5,prev_abs k3 repl': dict(covs=('vol20', 'vol5', 'prev_abs')),
    'maha vol20 k3 repl': dict(covs=('vol20',)),
    'maha vol20,vol5 k3 repl': dict(covs=('vol20', 'vol5')),
    'maha vol20,prev_abs k3 repl': dict(covs=('vol20', 'prev_abs')),
    'maha vol20,range5 k3 repl': dict(covs=('vol20', 'range5')),
    'maha vol20,ret5 k3 repl': dict(covs=('vol20', 'ret5'), loglev=False),
    'euclid vol20,vol5,prev_abs k3 repl': dict(covs=('vol20', 'vol5', 'prev_abs'), dist='euclid'),
    'maha vol20,vol5,prev_abs k3 NOrepl': dict(covs=('vol20', 'vol5', 'prev_abs'), replace=False),
    'maha vol20 k3 NOrepl': dict(covs=('vol20',), replace=False),
    'maha vol5,range5 k3 repl': dict(covs=('vol5', 'range5')),
}
res = {}
for nm, kw in specs.items():
    m = match(s, **kw)
    res[nm] = evr_by_regime(m)
R = pd.DataFrame(res); R.insert(0, 'sheet', sheet)
R = R.loc[sheet.index.intersection(R.index)]
pd.set_option('display.width', 250); pd.set_option('display.max_columns', 30)
print(R.round(2).to_string())
err = R.drop(columns='sheet').sub(R.sheet, axis=0)
errx = err.drop(index=['R13'], errors='ignore')    # R13 (CAS) differs mechanically; judge on R01-R12
print('\nMAE / max abs error vs sheet (R01-R12):')
print(pd.DataFrame({'MAE': errx.abs().mean(), 'max': errx.abs().max(), 'corr': R.drop(columns='sheet').drop(index='R13').corrwith(R.sheet.drop('R13'))}).round(3).sort_values('MAE'))
