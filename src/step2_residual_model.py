"""
Step 2 - Residual ("expected late-session move") model for ExpiryWatch India.

Idea: learn what the final-15-minute move (15:15-15:30) normally looks like given
market state known BEFORE 15:15, using NON-EXPIRY S1 days only. Then score every
day, in particular expiry days: residual = actual - expected. A positive, large
residual means "bigger close than market state predicts" (surveillance-relevant,
NOT evidence of manipulation).

Run from the project root:   python src/step2_residual_model.py
Outputs (in outputs/):
    residual_scores.csv      one row per S1 day: expected, residual, z, flags
    expiry_residuals_walkforward.csv                   expiry days 2022+, out-of-sample residual
    expiry_residuals_RETROSPECTIVE_uses_future_years.csv  all expiry days, leave-one-year-out (descriptive only)
    step2_summary.txt        all headline numbers (paste into report)
    importance.csv           feature importance (SHAP if installed, else permutation)
"""
import sys, warnings
import numpy as np
import pandas as pd
from scipy import stats
from sklearn.ensemble import GradientBoostingRegressor
from sklearn.linear_model import Ridge
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.inspection import permutation_importance

warnings.filterwarnings("ignore")

# ----------------------------------------------------------------- CONFIG
DAILY = "outputs/daily_features.parquet"
EXPIRY = "outputs/expiry_features.parquet"      # optional join for weekly/monthly split
COL = dict(                                       # <-- rename here if your columns differ
    date="date",             # a date column, or the index will be used
    y_abs_r4="y_abs_r4",
    y_range4="y_range4",
    is_expiry="is_expiry",   # 1/0 or True/False
    settle="settle",         # 'S1' / 'S2'
    trend="trend_to_1515",
)
# rv20_pct is deliberately NOT used: it needs ~250 days of history, so it silently drops 80 days and
# 18 expiries (not just the 4 warm-up ones). weekday is NOT used: in the Thursday era every Thursday is an
# expiry, so the training pool (non-expiry days) has no Thursdays and the model would extrapolate.
BASE_FEATURES = ["rv20", "r5", "prev_absret", "rv_first3",
                 "abs_trend", "strike50", "gap", "event"]
EXPECTED_S1_EXPIRIES_WITH_CONTROLS = 367     # 380 - 9 CAS - 4 warm-up
FLOOR = 1e-4                  # 1 bp floor so 2 zero-return days don't create log(0) outliers
WF_FIRST_TEST_YEAR = 2022     # walk-forward: train on years < test year
REPORT_SPLIT_YEAR = 2023      # report-style split: train <= 2022, test >= 2023
SEED = 0
out = []
NEG_CONTROLS = ["2020-03-12", "2023-01-25", "2024-02-01"]


def log(*a):
    s = " ".join(str(x) for x in a)
    print(s)
    out.append(s)


def r2(y, p):
    return 1 - ((y - p) ** 2).sum() / ((y - y.mean()) ** 2).sum()


def make_gbr():
    return GradientBoostingRegressor(max_depth=2, n_estimators=150, learning_rate=0.03,
                                     subsample=0.7, min_samples_leaf=20, random_state=SEED)


def make_ridge():
    return make_pipeline(StandardScaler(), Ridge(alpha=10.0))


# ----------------------------------------------------------------- LOAD
d = pd.read_parquet(DAILY)
missing = [c for c in COL.values() if c not in d.columns and c != COL["date"]]
if missing:
    sys.exit(f"Columns not found: {missing}\nAvailable: {list(d.columns)}\nEdit COL at top of script.")
if COL["date"] in d.columns:
    d["date"] = pd.to_datetime(d[COL["date"]])
else:
    d["date"] = pd.to_datetime(d.index)
d = d.sort_values("date").reset_index(drop=True)

d["is_exp"] = d[COL["is_expiry"]].astype(int)
d["abs_trend"] = d[COL["trend"]].abs()
d["weekday"] = d["date"].dt.dayofweek
d["year"] = d["date"].dt.year

# S1 only: from 3 Aug 2026 the last bar is an auction print, not comparable
d = d[d[COL["settle"]] == "S1"].copy()
feats = [f for f in BASE_FEATURES if f in d.columns]
for f in set(BASE_FEATURES) - set(feats):
    log(f"WARNING: feature '{f}' not in table, skipped")

targets = {"log_r4": np.log(np.maximum(d[COL["y_abs_r4"]], FLOOR))}
if COL["y_range4"] in d.columns:
    targets["log_range4"] = np.log(np.maximum(d[COL["y_range4"]], FLOOR))
for k, v in targets.items():
    d["y_" + k] = v

n_before_days, n_before_exp = len(d), int(d.is_exp.sum())
lost = d[d[feats + ["y_" + k for k in targets]].isna().any(axis=1)]
d = d.dropna(subset=feats + ["y_" + k for k in targets]).reset_index(drop=True)
log(f"Warm-up rows dropped (NaN features): {len(lost)} days, of which {int(lost.is_exp.sum())} expiries "
    f"(S1 expiries {n_before_exp} -> {int(d.is_exp.sum())})")
if int(d.is_exp.sum()) != EXPECTED_S1_EXPIRIES_WITH_CONTROLS:
    log(f"WARNING: expected {EXPECTED_S1_EXPIRIES_WITH_CONTROLS} model-ready S1 expiries, got {int(d.is_exp.sum())}. "
        f"Lost expiry dates: {[str(x.date()) for x in lost[lost.is_exp == 1]['date']]}")
log(f"S1 days used: {len(d)}  (expiry days: {int(d.is_exp.sum())}, non-expiry: {int((1-d.is_exp).sum())})")
log(f"Features: {feats}")
log(f"Zero-return floor: {FLOOR}\n")

# ----------------------------------------------------------------- expiry type (weekly / monthly)
# NOTE: this join must happen BEFORE `ne` is created below, so both d and ne carry expiry_type.
etype = None
try:
    e = pd.read_parquet(EXPIRY)
    if not any("date" in str(c).lower() for c in e.columns):
        e = e.reset_index()                      # expiry date is stored as the index
    dcol = next((c for c in e.columns if "date" in str(c).lower() and "expiry" in str(c).lower()), None) \
        or next((c for c in e.columns if str(c).lower() in ("date", "expiry_date", "expiry date")), None)
    tcol = next((c for c in e.columns if "type" in str(c).lower()), None)
    if dcol is None or tcol is None:
        raise KeyError(f"need an expiry-date and an expiry-type column; found {list(e.columns)[:15]}")
    m = e[[dcol, tcol]].copy()
    m.columns = ["date", "expiry_type"]
    m["date"] = pd.to_datetime(m["date"])
    d = d.merge(m, on="date", how="left")
    etype = "expiry_type"
    nmiss = int(d[d.is_exp == 1]["expiry_type"].isna().sum())
    log(f"Joined expiry type from {EXPIRY} (date col '{dcol}', type col '{tcol}'); expiry rows without a type: {nmiss}")
except Exception as ex:
    log("!!! WEEKLY/MONTHLY SPLIT SKIPPED (this is the key subgroup - fix before using results):", ex)

d.to_pickle("outputs/_step2_daily_cache.pkl")
ne = d[d.is_exp == 0].copy()      # frozen training pool: non-expiry days only

# ----------------------------------------------------------------- PART A: report-style split
log("=" * 70)
log("PART A - report-style split (train non-expiry <= 2022, test non-expiry >= 2023)")
log("=" * 70)
for tname in targets:
    y = "y_" + tname
    tr = ne[ne.year < REPORT_SPLIT_YEAR]
    te = ne[ne.year >= REPORT_SPLIT_YEAR]
    naive = r2(te[y], np.full(len(te), tr[y].mean()))
    for mname, mk in [("ridge", make_ridge), ("gbr", make_gbr)]:
        m = mk().fit(tr[feats], tr[y])
        log(f"[{tname}] {mname:5s} in-sample R2 {r2(tr[y], m.predict(tr[feats])):6.3f} | "
            f"OOS R2 {r2(te[y], m.predict(te[feats])):6.3f} | naive-mean OOS {naive:6.3f} "
            f"(n_train {len(tr)}, n_test {len(te)})")
log("Reference: the draft report quotes 15.2% in-sample / 5.5% out-of-sample (different feature set, "
    "expiry indicators included, so compare orders of magnitude, not decimals).\n")

# ----------------------------------------------------------------- PART B: walk-forward residuals
log("=" * 70)
log("PART B - walk-forward residuals (train on non-expiry days of earlier years only)")
log("=" * 70)
primary = "log_r4"
for tname in targets:
    y = "y_" + tname
    parts = []
    for yr in range(WF_FIRST_TEST_YEAR, int(d.year.max()) + 1):
        tr = ne[ne.year < yr]
        te = d[d.year == yr]
        if len(te) == 0 or len(tr) < 200:
            continue
        m = make_gbr().fit(tr[feats], tr[y])
        p = pd.DataFrame({"date": te["date"].values, "exp_wf_" + tname: m.predict(te[feats])})
        parts.append(p)
    wf = pd.concat(parts)
    d = d.merge(wf, on="date", how="left")
    d["res_wf_" + tname] = d[y] - d["exp_wf_" + tname]

    # leave-one-year-out (uses FUTURE years: for ranking/description only, NOT walk-forward)
    loyo = np.full(len(d), np.nan)
    for yr in sorted(d.year.unique()):
        tr = ne[ne.year != yr]
        idx = d.index[d.year == yr]
        m = make_gbr().fit(tr[feats], tr[y])
        loyo[idx] = d.loc[idx, y].values - m.predict(d.loc[idx, feats])
    d["res_retro_" + tname] = loyo

    # z-scores relative to the non-expiry OOS residual distribution
    ref = d[(d.is_exp == 0)]["res_wf_" + tname].dropna()
    d["z_wf_" + tname] = (d["res_wf_" + tname] - ref.mean()) / ref.std()
    ref2 = d[(d.is_exp == 0)]["res_retro_" + tname].dropna()
    d["z_retro_" + tname] = (d["res_retro_" + tname] - ref2.mean()) / ref2.std()

    ex = d[(d.is_exp == 1)]
    oos = d[(d.is_exp == 0) & d["res_wf_" + tname].notna()]
    log(f"\n[{tname}] walk-forward OOS R2 on non-expiry days {WF_FIRST_TEST_YEAR}+: "
        f"{r2(oos['y_' + tname], oos['exp_wf_' + tname]):.3f}")

    for label, col, sub in [("walk-forward (2022+)", "res_wf_" + tname, ex),
                            ("leave-one-year-out (all years)", "res_retro_" + tname, ex)]:
        s = sub[col].dropna()
        non = d[(d.is_exp == 0)][col].dropna()
        # PRIMARY inference: expiry residuals vs NON-EXPIRY residuals from the same model/period.
        # (A test against 0 is biased when the model drifts, e.g. final-bar ranges fell after 2022, so
        #  non-expiry residuals are not centred on 0. The non-expiry residuals are the correct benchmark.)
        diff = s.mean() - non.mean()
        tw, pw = stats.ttest_ind(s, non, equal_var=False)
        try:
            pm = stats.mannwhitneyu(s, non, alternative="two-sided").pvalue
        except Exception:
            pm = np.nan
        t0, p0 = stats.ttest_1samp(s, 0.0)
        log(f"  Expiry vs non-expiry residual, {label}: n_exp={len(s)} n_non={len(non)}  "
            f"expiry mean={s.mean():+.3f}  non-expiry mean={non.mean():+.3f}  "
            f"DIFFERENCE={diff:+.3f} (~{(np.exp(diff) - 1) * 100:+.0f}% in the final-bar measure)  "
            f"Welch t={tw:.2f} (p={pw:.4f})  Mann-Whitney p={pm:.4f}  "
            f"[naive test vs 0: t={t0:.2f}, biased if non-expiry mean != 0]")
        if etype and etype in sub.columns:
            for k, g in sub.dropna(subset=[col]).groupby(etype):
                gs = g[col]
                dk = gs.mean() - non.mean()
                tk, pk = stats.ttest_ind(gs, non, equal_var=False)
                log(f"      {k:8s} n={len(gs):3d}  difference vs non-expiry={dk:+.3f} "
                    f"(~{(np.exp(dk) - 1) * 100:+.0f}%)  share above non-expiry mean={np.mean(gs > non.mean()):.2f}  "
                    f"Welch t={tk:.2f} (p={pk:.4f})")

# ----------------------------------------------------------------- outputs
cols = ["date", "year", "is_exp", "regime"] if "regime" in d.columns else ["date", "year", "is_exp"]
if etype:
    cols.append(etype)
cols += [c for c in d.columns if c.startswith(("y_", "exp_wf_", "res_", "z_"))]
d[cols].to_csv("outputs/residual_scores.csv", index=False)
ex = d[d.is_exp == 1][cols].sort_values("res_retro_" + primary, ascending=False)
# walk-forward (genuinely out-of-sample, 2022+) ranking
exwf = d[(d.is_exp == 1) & d["res_wf_" + primary].notna()][cols].sort_values("res_wf_" + primary, ascending=False)
exwf.to_csv("outputs/expiry_residuals_walkforward.csv", index=False)
# retrospective ranking: trained on other years INCLUDING FUTURE ones -> descriptive only, never evaluation
ex.to_csv("outputs/expiry_residuals_RETROSPECTIVE_uses_future_years.csv", index=False)
log("\nTop 10 expiries, WALK-FORWARD residual (2022+, out-of-sample):")
log(exwf.head(10)[["date"] + ([etype] if etype else []) + ["res_wf_" + primary, "z_wf_" + primary]].to_string(index=False))
log("\nTop 15 expiries, RETROSPECTIVE (leave-one-year-out, uses future years; descriptive only, not walk-forward):")
log(ex.head(15)[["date"] + ([etype] if etype else []) + ["res_retro_" + primary, "z_retro_" + primary,
                                                         "res_wf_" + primary]].to_string(index=False))

# negative controls (listed-event expiries)
for dt in NEG_CONTROLS:
    r = ex[ex.date == pd.Timestamp(dt)]
    if len(r):
        rank = int((ex["res_retro_" + primary] > r["res_retro_" + primary].iloc[0]).sum()) + 1
        log(f"Negative control {dt}: residual {r['res_retro_' + primary].iloc[0]:+.2f}, rank {rank} of {len(ex)}")

# ----------------------------------------------------------------- importance / SHAP
y = "y_" + primary
m = make_gbr().fit(ne[feats], ne[y])
try:
    import shap
    sv = shap.TreeExplainer(m).shap_values(d[feats])
    imp = pd.Series(np.abs(sv).mean(0), index=feats).sort_values(ascending=False)
    shap_df = pd.DataFrame(sv, columns=["shap_" + f for f in feats])
    shap_df.insert(0, "date", d["date"].values)
    shap_df[d.is_exp.values == 1].to_csv("outputs/expiry_shap.csv", index=False)
    log("\nMean |SHAP| (primary target, model fit on all non-expiry days; for explanation, not scoring):")
except ImportError:
    pi = permutation_importance(m, ne[feats], ne[y], n_repeats=10, random_state=SEED)
    imp = pd.Series(pi.importances_mean, index=feats).sort_values(ascending=False)
    log("\nPermutation importance (install `shap` for per-expiry attributions):")
imp.to_csv("outputs/importance.csv", header=["importance"])
log(imp.round(4).to_string())

open("outputs/step2_summary.txt", "w").write("\n".join(out))
log("\nSaved: residual_scores.csv, expiry_residuals_walkforward.csv, expiry_residuals_RETROSPECTIVE_uses_future_years.csv, expiry_shap.csv (if shap), importance.csv, step2_summary.txt")