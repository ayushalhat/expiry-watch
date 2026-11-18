"""
wp5_wp6_results.py - computes the remaining WP5 (partial) and WP6 results and bundles EVERYTHING needed for the
reports into  results_package/  (+ results_package.zip).   ExpiryWatch India (NIFTY, spot-only, Tier A).

Run from the project root AFTER Steps 2-5 have run:
    python src/wp5_wp6_results.py

New numbers computed here
  WP5  settlement-timing tables (by type and era), concentration of the final-bar effect, strike alignment,
       conditional next-day reversal, recurrence / serial-dependence tests
  WP6  model-agreement with CIs, consensus-vs-chance (permutation), consensus profile, tier cut-off sensitivity,
       top-MIRS table
Everything is descriptive/exploratory unless stated; p-values are NOT a confirmatory family (BH q-values are added
within each table). Spot-only data: no claim about intent or manipulation is possible.
"""
import os, shutil, zipfile, warnings
import numpy as np
import pandas as pd
from scipy import stats

warnings.filterwarnings("ignore")

# ------------------------------------------------------------------ CONFIG
EXPIRY_PARQ = "outputs/expiry_features.parquet"
WP_XLSX = "data/ExpiryWatch_NIFTY_WP1_WP2.xlsx"
F = dict(
    mirs_wf="outputs/step4_mirs_walkforward.csv",
    mirs_retro="outputs/step4_mirs_RETROSPECTIVE.csv",
    ml_A="outputs/step3v2_scores_A.csv",
    ml_B="outputs/step3v2_scores_B.csv",
    ml_R="outputs/step3v2_scores_RETROSPECTIVE_in_sample.csv",
    res_wf="outputs/expiry_residuals_walkforward.csv",
)
COPY = [  # (source, destination inside the package) - copied if present, listed as MISSING otherwise
    ("outputs/step2_summary.txt", "from_steps/step2_summary.txt"),
    ("outputs/importance.csv", "from_steps/step2_importance.csv"),
    ("outputs/expiry_shap.csv", "from_steps/step2_expiry_shap.csv"),
    ("outputs/expiry_residuals_walkforward.csv", "from_steps/step2_expiry_residuals_walkforward.csv"),
    ("outputs/step3v2_diagnostics.txt", "from_steps/step3v2_diagnostics.txt"),
    ("outputs/step3v2_scores_A.csv", "from_steps/step3v2_scores_A.csv"),
    ("outputs/step3v2_scores_B.csv", "from_steps/step3v2_scores_B.csv"),
    ("outputs/step3v2_scores_RETROSPECTIVE_in_sample.csv", "from_steps/step3v2_scores_RETRO.csv"),
    ("outputs/step4_diagnostics.txt", "from_steps/step4_diagnostics.txt"),
    ("outputs/step4_mirs_walkforward.csv", "from_steps/step4_mirs_walkforward.csv"),
    ("outputs/step4_mirs_RETROSPECTIVE.csv", "from_steps/step4_mirs_RETROSPECTIVE.csv"),
    ("outputs/forensics/evidence_packs.md", "from_steps/forensics/evidence_packs.md"),
    ("outputs/forensics/forensics_summary.csv", "from_steps/forensics/forensics_summary.csv"),
]
PKG = "results_package"
SEED, N_PERM, N_BOOT = 20261116, 5000, 2000
rng = np.random.RandomState(SEED)
summary = []


def log(*a):
    s = " ".join(str(x) for x in a)
    print(s)
    summary.append(s)


def bh(p):
    p = np.asarray(p, float)
    q = np.full(len(p), np.nan)
    ok = ~np.isnan(p)
    pv = p[ok]
    n = len(pv)
    if n == 0:
        return q
    order = np.argsort(pv)
    ranked = pv[order] * n / (np.arange(n) + 1)
    ranked = np.minimum.accumulate(ranked[::-1])[::-1]
    out = np.empty(n)
    out[order] = np.minimum(ranked, 1)
    q[ok] = out
    return q


os.makedirs(PKG + "/WP5", exist_ok=True)
os.makedirs(PKG + "/WP6", exist_ok=True)

# ------------------------------------------------------------------ LOAD
e = pd.read_parquet(EXPIRY_PARQ)
e.index = pd.to_datetime(e.index)
e = e[e["model_ok"]].copy()
assert len(e) == 367, f"expected 367 model_ok expiries, got {len(e)}"

raw = pd.read_excel(WP_XLSX, sheet_name="WP2 Expiry vs Control", header=None)
w = raw.iloc[2:].copy()
w["date"] = pd.to_datetime(w[1])
w = w.set_index("date")
POS = {"r4_exp": 30, "r4_ctrl": 31, "r4_diff": 32, "rng_exp": 33, "rng_ctrl": 34, "rng_diff": 35,
       "lbs_exp": 36, "lbs_ctrl": 37, "lbs_diff": 38, "rev_exp": 48, "rev_ctrl": 49, "rev_diff": 50}
w2 = pd.DataFrame({k: pd.to_numeric(w[v], errors="coerce") for k, v in POS.items()})
d = e[["expiry_type", "regime", "evr", "close", "events_pm5d", "reversal_ratio"]].join(w2, how="left")
d["era"] = np.where(d.index < pd.Timestamp("2023-01-01"), "2019-2022", "2023-2026")
log("=" * 70 + "\nRESULTS PACKAGE - WP5 (partial) and WP6\n" + "=" * 70)
log(f"model_ok expiries: {len(d)}  (weekly {int((d.expiry_type == 'Weekly').sum())}, monthly {int((d.expiry_type == 'Monthly').sum())})")
log("NaN in WP2 difference columns:", int(d[["r4_diff", "rng_diff", "lbs_diff", "rev_diff"]].isna().sum().sum()))

# ================================================================== WP5.1 settlement timing by group
rows = []
groups = {"All S1 expiries": d.index == d.index, "Weekly": d.expiry_type == "Weekly", "Monthly": d.expiry_type == "Monthly",
          "Era 2019-2022 (all)": d.era == "2019-2022", "Era 2023-2026 (all)": d.era == "2023-2026",
          "Weekly 2019-2022": (d.expiry_type == "Weekly") & (d.era == "2019-2022"),
          "Weekly 2023-2026": (d.expiry_type == "Weekly") & (d.era == "2023-2026"),
          "Monthly 2019-2022": (d.expiry_type == "Monthly") & (d.era == "2019-2022"),
          "Monthly 2023-2026": (d.expiry_type == "Monthly") & (d.era == "2023-2026")}
for g, mask in groups.items():
    sub = d[np.asarray(mask)]
    for meas, lab in [("r4", "Final-15-min absolute return"), ("rng", "Final-15-min range"), ("lbs", "Last-bar share of path")]:
        x = sub[f"{meas}_diff"].dropna()
        ctrl = sub[f"{meas}_ctrl"].mean()
        t, p = stats.ttest_1samp(x, 0.0)
        try:
            pw = stats.wilcoxon(x).pvalue
        except Exception:
            pw = np.nan
        rows.append(dict(group=g, measure=lab, n=len(x), expiry_mean=sub[f"{meas}_exp"].mean(), control_mean=ctrl,
                         mean_diff=x.mean(), rel_diff_pct=(x.mean() / ctrl * 100 if meas != "lbs" else np.nan),
                         median_diff=x.median(), share_expiries_above_controls=(x > 0).mean(), t=t, p_t=p, p_wilcoxon=pw))
t51 = pd.DataFrame(rows)
t51["q_BH_within_table"] = bh(t51["p_t"])
t51.to_csv(PKG + "/WP5/wp5_1_settlement_timing_by_group.csv", index=False)
log("\n[WP5.1] Settlement timing: expiry minus matched controls")
for g in ["All S1 expiries", "Weekly", "Monthly", "Era 2019-2022 (all)", "Era 2023-2026 (all)"]:
    r = t51[(t51.group == g) & (t51.measure == "Final-15-min absolute return")].iloc[0]
    r2 = t51[(t51.group == g) & (t51.measure == "Final-15-min range")].iloc[0]
    log(f"  {g:22s} n={int(r.n):3d} | |r4| diff {r.mean_diff * 1e4:+.2f} bps ({r.rel_diff_pct:+.0f}%), p={r.p_t:.3f} | "
        f"range diff {r2.mean_diff * 1e4:+.2f} bps ({r2.rel_diff_pct:+.0f}%), p={r2.p_t:.3f}")

# ================================================================== WP5.2 concentration of the effect
rows = []
for g, mask in {"All": d.index == d.index, "Weekly": d.expiry_type == "Weekly", "Monthly": d.expiry_type == "Monthly"}.items():
    sub = d[np.asarray(mask)]
    for meas in ["r4_diff", "rng_diff"]:
        x = sub[meas].dropna().sort_values(ascending=False)
        pos_total, net_total = x.clip(lower=0).sum(), x.sum()
        for q in (0.05, 0.10, 0.20):
            k = int(np.ceil(q * len(x)))
            rows.append(dict(group=g, measure=meas, top_fraction=q, n_top=k,
                             share_of_total_positive_excess=x.iloc[:k].clip(lower=0).sum() / pos_total,
                             share_of_net_excess=x.iloc[:k].sum() / net_total if net_total > 0 else np.nan))
t52 = pd.DataFrame(rows)
t52.to_csv(PKG + "/WP5/wp5_2_effect_concentration.csv", index=False)
log("\n[WP5.2] Concentration: share of the total positive excess final-bar activity contributed by the top 10% of expiries")
for g in ["All", "Weekly", "Monthly"]:
    for meas in ["r4_diff", "rng_diff"]:
        r = t52[(t52.group == g) & (t52.measure == meas) & (t52.top_fraction == 0.10)].iloc[0]
        log(f"  {g:8s} {meas:8s}: top 10% = {int(r.n_top)} expiries -> {r.share_of_total_positive_excess:.0%} of positive excess; "
            f"{r.share_of_net_excess:.0%} of NET excess (>100% means the rest net to below zero)")

# ================================================================== WP5.3 strike alignment (unweighted)
d["dist50"] = np.minimum(d["close"] % 50, 50 - d["close"] % 50) / 50
d["dist100"] = np.minimum(d["close"] % 100, 100 - d["close"] % 100) / 100
X_NEAR = 0.05                     # normalised distance <= 0.05 ; under no pinning P = 2*0.05 = 0.10
rows = []
wf = pd.read_csv(F["mirs_wf"], index_col=0, parse_dates=True) if os.path.exists(F["mirs_wf"]) else pd.DataFrame()
grp = {"All": d.index == d.index, "Weekly": d.expiry_type == "Weekly", "Monthly": d.expiry_type == "Monthly"}
if len(wf):
    top20 = set(wf.nlargest(20, "MIRS").index)
    orange = set(wf.index[wf.tier == "Orange"])
    grp["Top-20 MIRS (walk-forward)"] = d.index.isin(top20)
    grp["All other scored (walk-forward)"] = d.index.isin(set(wf.index) - top20)
for g, mask in grp.items():
    sub = d[np.asarray(mask)]
    for grid in ("dist50", "dist100"):
        x = sub[grid].dropna()
        k = int((x <= X_NEAR).sum())
        pb = stats.binomtest(k, len(x), 2 * X_NEAR).pvalue if len(x) else np.nan
        rows.append(dict(group=g, grid=grid, n=len(x), mean_distance=x.mean(), expected_mean=0.25,
                         share_within_0_05=k / len(x) if len(x) else np.nan, expected_share=2 * X_NEAR, p_binomial=pb))
t53 = pd.DataFrame(rows)
t53["q_BH_within_table"] = bh(t53["p_binomial"])
t53.to_csv(PKG + "/WP5/wp5_3_strike_alignment.csv", index=False)
log("\n[WP5.3] Strike alignment (UNWEIGHTED by open interest; close = 15:30 spot close, not the settlement VWAP)")
for _, r in t53[t53.group.isin(["All", "Monthly", "Top-20 MIRS (walk-forward)"])].iterrows():
    log(f"  {r.group:28s} {r.grid}: n={int(r.n)} mean distance {r.mean_distance:.3f} (no-pinning 0.250); "
        f"within 0.05: {r.share_within_0_05:.1%} vs {r.expected_share:.0%} expected, p={r.p_binomial:.3f}")

# ================================================================== WP5.4 conditional reversal
rows = []
d["r4_diff_q"] = d.groupby("expiry_type")["r4_diff"].transform(lambda s: s.rank(pct=True))
cond = {"All": d.index == d.index, "Weekly": d.expiry_type == "Weekly", "Monthly": d.expiry_type == "Monthly",
        "Large final-bar move (top quartile within type)": d.r4_diff_q >= 0.75,
        "Other expiries": d.r4_diff_q < 0.75,
        "No listed event within 5 days": d.events_pm5d.fillna(0) == 0,
        "Listed event within 5 days": d.events_pm5d.fillna(0) >= 1,
        "Large move AND no listed event": (d.r4_diff_q >= 0.75) & (d.events_pm5d.fillna(0) == 0)}
if len(wf):
    cond["High settlement-timing T>=0.80 (walk-forward)"] = d.index.isin(set(wf.index[wf["T"] >= 0.80]))
for g, mask in cond.items():
    x = d.loc[np.asarray(mask), "rev_diff"].dropna()
    if len(x) < 5:
        continue
    t, p = stats.ttest_1samp(x, 0.0)
    rows.append(dict(group=g, n=len(x), mean_reversal_diff_pct_pts=x.mean() * 100, median=x.median() * 100,
                     share_positive=(x > 0).mean(), t=t, p_t=p))
t54 = pd.DataFrame(rows)
t54["q_BH_within_table"] = bh(t54["p_t"])
t54.to_csv(PKG + "/WP5/wp5_4_reversal_conditional.csv", index=False)
log("\n[WP5.4] Next-day signed reversal, expiry minus controls (positive = next day moves against the expiry-day direction)")
for _, r in t54.iterrows():
    log(f"  {r.group:50s} n={int(r.n):3d} mean {r.mean_reversal_diff_pct_pts:+.3f} pp  share>0 {r.share_positive:.2f}  p={r.p_t:.3f}  q={r.q_BH_within_table:.3f}")

# ================================================================== WP5.5 recurrence / serial dependence
rows = []
txt = []
for meas, lab in [("rng_diff", "final-15-min range diff"), ("r4_diff", "final-15-min |return| diff"), ("lbs_diff", "last-bar share diff")]:
    for et in ["Weekly", "Monthly"]:
        x = d[d.expiry_type == et].sort_index()[meas].dropna().values
        if len(x) < 20:
            continue
        r_obs = np.corrcoef(x[:-1], x[1:])[0, 1]
        perm = np.array([np.corrcoef(*(lambda y: (y[:-1], y[1:]))(rng.permutation(x)))[0, 1] for _ in range(N_PERM)])
        p_perm = (np.abs(perm) >= abs(r_obs)).mean()
        thr = np.quantile(x, 0.90)
        hi = (x >= thr).astype(int)
        pairs_obs = int((hi[:-1] * hi[1:]).sum())
        pairs_perm = np.array([(lambda h: (h[:-1] * h[1:]).sum())(rng.permutation(hi)) for _ in range(N_PERM)])
        rows.append(dict(measure=lab, expiry_type=et, n=len(x), lag1_autocorr=r_obs, p_permutation=p_perm,
                         n_top_decile=int(hi.sum()), consecutive_top_decile_pairs=pairs_obs,
                         expected_pairs_if_random=pairs_perm.mean(), p_pairs_permutation=(pairs_perm >= pairs_obs).mean()))
t55 = pd.DataFrame(rows)
t55["q_BH_autocorr"] = bh(t55["p_permutation"])
t55["q_BH_pairs"] = bh(t55["p_pairs_permutation"])      # 6 tests: expect ~0.3 nominal hits by chance
t55.to_csv(PKG + "/WP5/wp5_5_recurrence_serial_dependence.csv", index=False)
log("\n[WP5.5] Recurrence: do unusually active closes cluster in time? (permutation tests, consecutive same-type expiries)")
for _, r in t55.iterrows():
    log(f"  {r.measure:28s} {r.expiry_type:8s} n={int(r.n):3d} lag-1 autocorr {r.lag1_autocorr:+.3f} (perm p={r.p_permutation:.3f}); "
        f"top-decile consecutive pairs {int(r.consecutive_top_decile_pairs)} vs {r.expected_pairs_if_random:.1f} expected (p={r.p_pairs_permutation:.3f}, BH q={r.q_BH_pairs:.3f})")
# quarter-end months and year profile
mo = d[d.expiry_type == "Monthly"].copy()
mo["quarter_end"] = mo.index.month.isin([3, 6, 9, 12])
rows = []
for meas in ["r4_diff", "rng_diff", "lbs_diff"]:
    a, b = mo.loc[mo.quarter_end, meas].dropna(), mo.loc[~mo.quarter_end, meas].dropna()
    rows.append(dict(measure=meas, n_quarter_end=len(a), n_other_monthly=len(b), mean_quarter_end=a.mean(), mean_other=b.mean(),
                     p_mannwhitney=stats.mannwhitneyu(a, b, alternative="two-sided").pvalue))
t55b = pd.DataFrame(rows)
t55b["q_BH"] = bh(t55b["p_mannwhitney"])
t55b.to_csv(PKG + "/WP5/wp5_5b_quarter_end_monthlies.csv", index=False)
thr_all = d.groupby("expiry_type")["rng_diff"].transform(lambda s: s.quantile(0.90))
yr = (d["rng_diff"] >= thr_all).groupby(d.index.year).agg(["sum", "count"])
yr["share_top_decile"] = yr["sum"] / yr["count"]
yr.to_csv(PKG + "/WP5/wp5_5c_top_decile_by_year.csv")
log("  Quarter-end vs other monthly expiries (final-bar differences): " + "; ".join(
    f"{r.measure}: {r.mean_quarter_end:+.5f} vs {r.mean_other:+.5f} (p={r.p_mannwhitney:.3f}, n={int(r.n_quarter_end)}/{int(r.n_other_monthly)})" for _, r in t55b.iterrows()))
log("  Share of expiries in each year's type-specific top decile of final-15-min range difference: " +
    ", ".join(f"{int(i)}: {v:.0%}" for i, v in yr["share_top_decile"].items()))

# ================================================================== WP6.1 model agreement
mlA = pd.read_csv(F["ml_A"], index_col=0, parse_dates=True) if os.path.exists(F["ml_A"]) else pd.DataFrame()
mlB = pd.read_csv(F["ml_B"], index_col=0, parse_dates=True) if os.path.exists(F["ml_B"]) else pd.DataFrame()
mlR = pd.read_csv(F["ml_R"], index_col=0, parse_dates=True) if os.path.exists(F["ml_R"]) else pd.DataFrame()
rows = []
for name, ml in [("Version A (walk-forward, behaviour features)", mlA), ("Version B (walk-forward 2024+, + residual)", mlB),
                 ("Retrospective (in-sample)", mlR)]:
    if not len(ml):
        continue
    for a, b in [("pct_IF", "pct_LOF"), ("pct_IF", "pct_SVM"), ("pct_LOF", "pct_SVM")]:
        r, p = stats.spearmanr(ml[a], ml[b])
        bs = []
        for _ in range(N_BOOT):
            ix = rng.randint(0, len(ml), len(ml))
            bs.append(stats.spearmanr(ml[a].values[ix], ml[b].values[ix])[0])
        rows.append(dict(version=name, pair=f"{a[4:]} vs {b[4:]}", n=len(ml), spearman=r, p=p,
                         ci95_low=np.percentile(bs, 2.5), ci95_high=np.percentile(bs, 97.5)))
t61 = pd.DataFrame(rows)
t61.to_csv(PKG + "/WP6/wp6_1_model_agreement.csv", index=False)
log("\n[WP6.1] Agreement between the three unsupervised models (Spearman, bootstrap 95% CI)")
for _, r in t61.iterrows():
    log(f"  {r.version:46s} {r.pair:10s} n={int(r.n):3d} rho={r.spearman:+.3f} [{r.ci95_low:+.2f}, {r.ci95_high:+.2f}] p={r.p:.3f}")

# ================================================================== WP6.2 consensus vs chance (permutation)
rows = []
for name, ml in [("Version A", mlA), ("Version B", mlB), ("Retrospective", mlR)]:
    if not len(ml):
        continue
    M = ml[["pct_IF", "pct_LOF", "pct_SVM"]].values
    for thr in (0.80, 0.90):
        obs2 = int(((M >= thr).sum(axis=1) >= 2).sum())
        obs3 = int(((M >= thr).sum(axis=1) == 3).sum())
        c2, c3 = [], []
        for _ in range(N_PERM):
            Mp = np.column_stack([rng.permutation(M[:, j]) for j in range(3)])
            k = (Mp >= thr).sum(axis=1)
            c2.append((k >= 2).sum())
            c3.append((k == 3).sum())
        rows.append(dict(version=name, threshold=thr, n=len(M), observed_ge2_of_3=obs2, expected_ge2_if_independent=np.mean(c2),
                         p_perm_ge2=(np.array(c2) >= obs2).mean(), observed_all3=obs3, expected_all3=np.mean(c3),
                         p_perm_all3=(np.array(c3) >= obs3).mean()))
t62 = pd.DataFrame(rows)
t62.to_csv(PKG + "/WP6/wp6_2_consensus_vs_chance.csv", index=False)
log("\n[WP6.2] Expiries flagged by >=2 of 3 models vs what independence would give (permutation)")
for _, r in t62.iterrows():
    log(f"  {r.version:14s} thr {r.threshold:.2f}: >=2 models: {int(r.observed_ge2_of_3)} vs {r.expected_ge2_if_independent:.1f} expected (p={r.p_perm_ge2:.3f}); "
        f"all 3: {int(r.observed_all3)} vs {r.expected_all3:.2f} (p={r.p_perm_all3:.3f})")

# ================================================================== WP6.3 consensus profile
if len(mlA) and os.path.exists(F["res_wf"]):
    res = pd.read_csv(F["res_wf"], parse_dates=["date"]).set_index("date")
    g = mlA.join(res[["res_wf_log_r4"]], how="left").join(d[["evr", "rng_diff", "lbs_diff", "expiry_type"]], rsuffix="_d", how="left")
    rows = []
    for thr in (0.80, 0.90):
        flag = (g[["pct_IF", "pct_LOF", "pct_SVM"]] >= thr).sum(axis=1) >= 2
        for lab, mask in [(f">=2 models above {thr:.2f}", flag), ("rest", ~flag)]:
            s = g[mask]
            rows.append(dict(threshold=thr, group=lab, n=len(s), mean_residual=s.res_wf_log_r4.mean(), mean_EVR=s.evr.mean(),
                             mean_range_diff_bps=s.rng_diff.mean() * 1e4, monthly_share=(s.expiry_type == "Monthly").mean()))
        a, b = g[flag], g[~flag]
        rows[-2]["p_mw_residual"] = stats.mannwhitneyu(a.res_wf_log_r4.dropna(), b.res_wf_log_r4.dropna()).pvalue
        rows[-2]["p_mw_EVR"] = stats.mannwhitneyu(a.evr.dropna(), b.evr.dropna()).pvalue
    t63 = pd.DataFrame(rows)
    t63.to_csv(PKG + "/WP6/wp6_3_consensus_profile.csv", index=False)
    rho, p = stats.spearmanr(g.dropna(subset=["res_wf_log_r4"])["pct_IF"].add(g.dropna(subset=["res_wf_log_r4"])["pct_LOF"]).add(
        g.dropna(subset=["res_wf_log_r4"])["pct_SVM"]), g.dropna(subset=["res_wf_log_r4"])["res_wf_log_r4"])
    log("\n[WP6.3] Profile of consensus-flagged expiries (PARTLY CIRCULAR: the ML features include the same final-bar behaviour)")
    log("  " + t63.round(4).to_string(index=False).replace("\n", "\n  "))
    log(f"  Gate G4: Spearman(ML sum of percentiles, Step 2 residual) = {rho:+.3f} (p={p:.3f}), n={g['res_wf_log_r4'].notna().sum()}")

# ================================================================== WP6.4 tier cut-off sensitivity + top table
if len(wf):
    rows = []
    for sp in (0.80, 0.85, 0.90, 0.95):
        s = (wf.A >= sp).astype(int) + (wf["T"] >= sp).astype(int) + (wf.R >= sp).astype(int) + (wf.Rec >= 0.5).astype(int)
        orange = (s >= 2) & (wf["T"] >= sp) & (wf.news_expl < 0.5)
        amber = (s >= 1) & ~orange
        rows.append(dict(signal_cutoff=sp, n_scored=len(wf), orange=int(orange.sum()), amber=int(amber.sum()),
                         green=int((~orange & ~amber).sum()), orange_dates="; ".join(str(x.date()) for x in wf.index[orange])))
    t64 = pd.DataFrame(rows)
    t64.to_csv(PKG + "/WP6/wp6_4_tier_cutoff_sensitivity.csv", index=False)
    top = wf.nlargest(20, "MIRS")[["expiry_type", "regime", "A", "T", "R", "Rec", "n_signals", "U", "news_expl", "MIRS", "tier"] +
                                  [c for c in ["ml_consensus", "ml_2of3_above_90"] if c in wf.columns]]
    top.to_csv(PKG + "/WP6/wp6_5_top20_mirs_walkforward.csv")
    log("\n[WP6.4] Tier counts vs the signal cut-off (walk-forward set)")
    log("  " + t64.drop(columns="orange_dates").to_string(index=False).replace("\n", "\n  "))
    log(f"  Green expiries among the top-20 by MIRS: {int((top.tier == 'Green').sum())}/20")

# ================================================================== PACKAGE
missing = []
for src, dst in COPY:
    if os.path.exists(src):
        os.makedirs(os.path.dirname(os.path.join(PKG, dst)), exist_ok=True)
        shutil.copy(src, os.path.join(PKG, dst))
    else:
        missing.append(src)
fdir = "outputs/forensics"
if os.path.isdir(fdir):
    os.makedirs(PKG + "/from_steps/forensics", exist_ok=True)
    for f in os.listdir(fdir):
        if f.endswith(".png"):
            shutil.copy(os.path.join(fdir, f), PKG + "/from_steps/forensics/" + f)
log("\n" + "=" * 70 + "\nPACKAGE CONTENTS\n" + "=" * 70)
if missing:
    log("MISSING (not copied - run the relevant step, or tell me why it is absent): " + ", ".join(missing))
log("INTERPRETATION RULE: all results rank SURVEILLANCE PRIORITY / describe market behaviour; none is evidence of manipulation.")
open(PKG + "/RESULTS_SUMMARY.txt", "w", encoding="utf-8").write("\n".join(summary))
with zipfile.ZipFile("results_package.zip", "w", zipfile.ZIP_DEFLATED) as z:
    for root, _, files in os.walk(PKG):
        for f in files:
            p = os.path.join(root, f)
            z.write(p, os.path.relpath(p, "."))
log(f"Wrote {PKG}/ and results_package.zip  ({sum(len(fs) for _, _, fs in os.walk(PKG))} files)")
