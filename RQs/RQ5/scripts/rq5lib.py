"""Shared pipeline for ExpiryWatch RQ5: sessions, expiry calendar, matched controls.

Everything is rebuilt from NIFTY_2h_OHLC_data.csv and the Regimes sheet of Database.xlsx
(the original Expiry_Events sheet was not supplied).
"""
import numpy as np
import pandas as pd

CSV = '/mnt/user-data/attachments/843f0391-b502-5c5c-83b5-b028439046ef/0287c687-NIFTY_2h_OHLC_data.csv'
XLSX = '/mnt/user-data/attachments/843f0391-b502-5c5c-83b5-b028439046ef/f186ebdc-Database.xlsx'
STD_BARS = ['09:15', '11:15', '13:15', '15:15']
CAS_START = pd.Timestamp('2026-08-03')
TUE_START = pd.Timestamp('2025-09-01')   # first week governed by Tuesday expiry
# 2021-02-24: NSE outage, trading halted ~11:40-15:00 and session extended; bar structure is not comparable
EXCLUDE_DATES = [pd.Timestamp('2021-02-24')]


def load_regimes():
    r = pd.read_excel(XLSX, sheet_name='Regimes', header=0).iloc[:14, :11]
    r = r[r['Regime ID'].astype(str).str.startswith('R')].copy()
    r['Start Date'] = pd.to_datetime(r['Start Date'])
    r['End Date'] = pd.to_datetime(r['End Date'])
    return r.reset_index(drop=True)


def load_sessions():
    """One row per regular session with all four standard bars present."""
    df = pd.read_csv(CSV)
    df['ts'] = pd.to_datetime(df['Date'].str[:19])
    df['d'] = df.ts.dt.normalize()
    df['hhmm'] = df.ts.dt.strftime('%H:%M')
    df = df[df.hhmm.isin(STD_BARS)]
    ok = df.groupby('d').hhmm.nunique() == 4
    df = df[df.d.isin(ok[ok].index)]
    df = df[df.d.dt.weekday < 5]
    df = df[~df.d.isin(EXCLUDE_DATES)]
    w = df.pivot(index='d', columns='hhmm', values=['Open', 'High', 'Low', 'Close'])
    s = pd.DataFrame(index=w.index)
    for i, b in enumerate(STD_BARS, start=1):
        s[f'O{i}'] = w[('Open', b)]; s[f'H{i}'] = w[('High', b)]
        s[f'L{i}'] = w[('Low', b)]; s[f'C{i}'] = w[('Close', b)]
        s[f'r{i}'] = np.log(s[f'C{i}'] / s[f'O{i}']) * 1e4
    s['RV'] = np.sqrt((s[['r1', 'r2', 'r3', 'r4']] ** 2).sum(axis=1))      # realised vol, bps
    s['late'] = s['r4']                                                    # 15:15-15:30 return, bps
    s['absL'] = s['late'].abs()
    s['open'] = s['O1']; s['close'] = s['C4']
    s['dayret'] = np.log(s.close / s.open) * 1e4
    s['prev_close'] = s.close.shift(1)
    s['gap_in'] = np.log(s.open / s.prev_close) * 1e4
    s['cc'] = np.log(s.close / s.prev_close) * 1e4                         # close-to-close return, bps
    s['rng'] = (s[['H1', 'H2', 'H3', 'H4']].max(axis=1) / s[['L1', 'L2', 'L3', 'L4']].min(axis=1) - 1) * 1e4
    s['last_var_share'] = s.r4 ** 2 / (s[['r1', 'r2', 'r3', 'r4']] ** 2).sum(axis=1)
    s['post_cas'] = s.index >= CAS_START
    return s


def build_calendar(s):
    """Weekly expiry per ISO week; monthly = last expiry of the calendar month.
    Target weekday Thu (Tue from the week of 2025-09-01). If target is not a regular session,
    expiry moves to the previous regular session in the same week."""
    dates = s.index
    weeks = pd.Series(dates, index=dates).groupby(dates.to_period('W-SUN'))
    exp = []
    for wk, ds in weeks:
        ds = list(ds)
        monday = wk.start_time
        tgt_wd = 1 if monday >= TUE_START else 3
        target = monday + pd.Timedelta(days=tgt_wd)
        if target in ds:
            e = target
        else:
            prev = [d for d in ds if d < target]
            if not prev:
                continue
            e = prev[-1]
        exp.append(e)
    exp = pd.DatetimeIndex(exp)
    # the first week is incomplete (data starts Wed 2019-06-26): Thursday 2019-06-27 is present -> kept
    s = s.copy()
    s['is_exp'] = s.index.isin(exp)
    ex = pd.Series(exp, index=exp)
    month_last = ex.groupby(exp.to_period('M')).max()
    s['is_monthly'] = s.index.isin(month_last.values)
    s['exp_type'] = np.where(~s.is_exp, 'none', np.where(s.is_monthly, 'monthly', 'weekly'))
    s['quarter_end'] = s.is_monthly & s.index.month.isin([3, 6, 9, 12])
    return s


def add_regimes(s, reg):
    s = s.copy()
    s['regime'] = None
    for _, r in reg.iterrows():
        end = r['End Date'] if pd.notna(r['End Date']) else pd.Timestamp('2100-01-01')
        s.loc[(s.index >= r['Start Date']) & (s.index <= end), 'regime'] = r['Regime ID']
    return s


def add_features(s):
    s = s.copy()
    s['vol20'] = s.cc.shift(1).rolling(20).std()           # prior 20-session close-to-close vol (bps)
    s['vol5'] = s.cc.shift(1).rolling(5).std()
    s['range5'] = s.rng.shift(1).rolling(5).mean()
    s['ret5'] = s.cc.shift(1).rolling(5).sum()
    s['prev_abs'] = s.cc.abs().shift(1)
    s['firstbars_vol'] = np.sqrt((s[['r1', 'r2', 'r3']] ** 2).sum(axis=1))   # vol of first three bars (known by 15:15)
    s['scale'] = s.absL.shift(1).rolling(20).mean()         # trailing typical |late move|
    s['weekday'] = s.index.weekday
    return s


def match_controls(s, k=3, covs=('vol20', 'vol5', 'prev_abs'), pre_cas_only=True):
    """Within-regime nearest-neighbour (Mahalanobis on log covariates), k controls per expiry, with replacement.
    Controls are regular non-expiry sessions of the same regime. Returns dict expiry_date -> list of control dates."""
    d = s.copy()
    if pre_cas_only:
        d = d[~d.post_cas]
    X = np.log(d[list(covs)].clip(lower=1e-3))
    ok = X.notna().all(axis=1) & d.regime.notna()
    d, X = d[ok], X[ok]
    cov = np.atleast_2d(np.cov(X.values.T))
    cinv = np.linalg.pinv(cov)
    out = {}
    for reg, grp in d.groupby('regime'):
        ex = grp[grp.is_exp]
        ct = grp[~grp.is_exp]
        if len(ct) < k or len(ex) == 0:
            continue
        Xc = X.loc[ct.index].values
        for e in ex.index:
            diff = Xc - X.loc[e].values
            dist = np.einsum('ij,jk,ik->i', diff, cinv, diff)
            idx = np.argsort(dist)[:k]
            out[e] = list(ct.index[idx])
    return out


def build_all():
    s = load_sessions()
    s = build_calendar(s)
    s = add_regimes(s, load_regimes())
    s = add_features(s)
    return s
