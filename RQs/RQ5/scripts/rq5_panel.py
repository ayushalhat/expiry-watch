"""RQ5 panel: late move L_t and post-expiry outcomes."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
import pandas as pd
import rq5lib as L

HORIZONS = ['gap', 'b1', 'b2', 'd1', 'd2', 'd3', 'd5']
HLABEL = {'gap': 'Next open', 'b1': 'Next 11:15', 'b2': 'Next 13:15', 'd1': 'Next close',
          'd2': '+2d close', 'd3': '+3d close', 'd5': '+5d close'}


def build_panel():
    s = L.build_all()
    close = s.close
    out = pd.DataFrame(index=s.index)
    out['gap'] = np.log(s.O1.shift(-1) / close) * 1e4
    out['b1'] = np.log(s.C1.shift(-1) / close) * 1e4
    out['b2'] = np.log(s.C2.shift(-1) / close) * 1e4
    for k in (1, 2, 3, 5):
        out[f'd{k}'] = np.log(close.shift(-k) / close) * 1e4
    # close-based targets that land on/after CAS go-live use a different closing mechanism -> drop
    dates = pd.Series(s.index, index=s.index)
    for k, col in [(1, 'd1'), (2, 'd2'), (3, 'd3'), (5, 'd5')]:
        out.loc[dates.shift(-k) >= L.CAS_START, col] = np.nan
    out.loc[dates.shift(-1) >= L.CAS_START, 'b1'] = np.nan   # first bar itself is pre-CAS-safe, keep conservative
    # session before the 2021-02-24 NSE outage: next trading day was excluded
    bad = pd.Timestamp('2021-02-23')
    out.loc[bad, HORIZONS] = np.nan
    s = s.join(out)
    s['sgn'] = np.sign(s.late)
    s['zL'] = s.absL / s.scale
    s['E'] = s.is_exp.astype(int)
    s['Ew'] = (s.exp_type == 'weekly').astype(int)
    s['Em'] = (s.exp_type == 'monthly').astype(int)
    for h in HORIZONS:
        s['Y_' + h] = -s.sgn * s[h]      # positive = reversal of the late move
    return s


def sample(s):
    d = s[(~s.post_cas) & s.vol20.notna() & s.scale.notna() & (s.sgn != 0)]
    return d
