"""
Step 4 - MIRS-lite (Market Integrity Risk Score, spot-only, DATA-LIMITED prototype). ExpiryWatch India.

    MIRS = U x (1 - LAMBDA x news_explanation)

U = weighted mean of four upward components, each a PAST-ONLY percentile (vs earlier expiries of the same type):
    A  whole-day anomaly ........ EVR
    T  settlement timing ........ mean of [Step 2 residual, final-15-min range diff, last-bar-share diff]
    R  reversal ................. next-day reversal ratio (weak evidence: WP2 q = 0.066 -> small weight)
    Rec recurrence .............. share of the previous 4 same-type expiries with T >= 0.90
news_explanation (0-1): listed event on the day (1.0); listed event within +-5 days (0.6);
                        extreme |overnight gap| (>= 80th past percentile, scaled up to 0.6).
NOT AVAILABLE with spot-only data (shown as "not testable", NOT silently zero): hedge, liquidity, rebalance,
arbitrage explanations; constituent concentration (C); price impact (I); cross-market alignment (X).
=> MIRS here is an UPPER BOUND on priority: missing explanation terms can only lower a true score.

Tiers (rule-based, following the proposal's definitions; MIRS is used to RANK within a tier, not to cut tiers because
an average of percentiles is compressed and never reaches extreme values):
    Orange = >= 2 independent signals among {A, T, R >= 90th percentile; recurrence >= 0.5}, INCLUDING the settlement-timing
             signal T (this project is about the settlement window: a volatile day with no settlement-timing evidence
             is not Orange), AND not news-explained
    Amber  = >= 1 signal, OR >= 2 signals that ARE news-explained   (unusual, but explainable / single-dimension)
    Green  = no signal
Only Green / Amber / Orange can be assigned. RED requires cross-market, settlement AND recurrence evidence
(proposal Section 10); cross-market evidence does not exist in this data, so Red is deliberately unassignable.

The Step 3 ML consensus is NOT in the base score (gate G4: ML has not shown stable out-of-sample value beyond the
econometric residual). It is reported alongside and as a sensitivity variant.

Run from the project root:   python src/step4_mirs_lite.py
Needs: outputs/expiry_features.parquet, Step 2 residual CSVs, Step 3 v2 score CSVs, data/*.xlsx
INTERPRETATION RULE: MIRS ranks SURVEILLANCE PRIORITY only. It is NOT evidence of manipulation or any legal violation.
"""
import warnings
import numpy as np
import pandas as pd
from scipy.stats import spearmanr

warnings.filterwarnings("ignore")

# ------------------------------------------------------------------ CONFIG
EXPIRY_PARQ = "outputs/expiry_features.parquet"
WP2_XLSX = "data/ExpiryWatch_NIFTY_WP1_WP2.xlsx"
RES_WF = "outputs/expiry_residuals_walkforward.csv"
RES_RETRO = "outputs/expiry_residuals_RETROSPECTIVE_uses_future_years.csv"
ML_WF = "outputs/step3v2_scores_A.csv"
ML_RETRO = "outputs/step3v2_scores_RETROSPECTIVE_in_sample.csv"

MIN_PAST = 10                                   # minimum past same-type expiries for a percentile
WEIGHTS = dict(A=0.25, T=0.45, R=0.10, Rec=0.20)  # illustrative; sensitivity-tested below
LAMBDA = 0.5                                    # max reduction of U when news fully explains
SIGNAL_PCT = 0.90                               # a component is a "signal" when its past-only percentile >= this
REC_SIGNAL = 0.50                               # recurrence signal: >= 2 of the previous 4 same-type expiries had T >= 0.90
EXPLAINED = 0.50                                # news_expl >= this counts as "explained" (listed event on/near the day)
NEG_CONTROLS = ["2020-03-12", "2023-01-25", "2024-02-01"]
N_DRAWS, SEED = 300, 7
out = []


def log(*a):
    s = " ".join(str(x) for x in a)
    print(s)
    out.append(s)


# ------------------------------------------------------------------ LOAD
e = pd.read_parquet(EXPIRY_PARQ)
e.index = pd.to_datetime(e.index)
e = e[e["model_ok"]].copy()
assert len(e) == 367, f"expected 367 model_ok expiries, got {len(e)}"

raw = pd.read_excel(WP2_XLSX, sheet_name="WP2 Expiry vs Control", header=None)
w = raw.iloc[2:].copy()
w["date"] = pd.to_datetime(w[1])
w = w.set_index("date")[[35, 38]].rename(columns={35: "range4_diff", 38: "lbs_diff"})
w = w.apply(pd.to_numeric, errors="coerce")

m = e[["expiry_type", "regime", "evr", "overnight_gap", "events_pm5d", "reversal_ratio"]].copy().join(w, how="left")
if "listed_event_overlap" in e.columns:
    ev = e["listed_event_overlap"].astype("string").str.strip()          # pandas 3: missing stays <NA>
    m["event_on_day"] = (ev.notna() & ~ev.fillna("").isin(["", "nan", "None", "NaN", "-", "—"])).astype(int)
else:
    m["event_on_day"] = 0
n_ev = int(m.event_on_day.sum())
log(f"Listed events detected ON an expiry day: {n_ev} (expected 3: 12 Mar 2020, 25 Jan 2023, 1 Feb 2024)")
assert n_ev in (0, 3), (f"event_on_day = {n_ev}; the listed_event_overlap column is not encoded as expected "
                        f"(unique values: {e['listed_event_overlap'].dropna().unique()[:8]}). Fix before continuing: "
                        f"a wrong flag would shrink every score.")
m["abs_gap"] = m["overnight_gap"].abs()


def past_pct(series, min_past=MIN_PAST):
    """Mid-rank percentile of each value vs strictly EARLIER expiries of the SAME type. NaN if too little history."""
    res = pd.Series(np.nan, index=series.index)
    for et in ["Weekly", "Monthly"]:
        idx = m.index[m.expiry_type == et].sort_values()
        vals = series.loc[idx]
        for i, dt in enumerate(idx):
            v = vals.iloc[i]
            pv = vals.iloc[:i].dropna()
            if pd.isna(v) or len(pv) < min_past:
                continue
            res.loc[dt] = (pv < v).mean() + 0.5 * (pv == v).mean()
    return res


pct_evr = past_pct(m["evr"])
pct_rng = past_pct(m["range4_diff"])
pct_lbs = past_pct(m["lbs_diff"])
pct_rev = past_pct(m["reversal_ratio"]).fillna(0.5)   # blank (|R|<0.25%) or too little history -> neutral 0.5
pct_gap = past_pct(m["abs_gap"])


def build(resid_series, ml_df, label):
    """Compute components, U, news explanation, MIRS, tiers for the expiries that have a residual."""
    d = m[["expiry_type", "regime"]].copy()
    d["resid"] = resid_series
    d = d[d["resid"].notna()].copy()
    pct_res = past_pct(resid_series.reindex(m.index))      # past-only percentile of the Step 2 residual
    d["A"] = pct_evr.reindex(d.index)
    d["T"] = pd.concat([pct_res.reindex(d.index), pct_rng.reindex(d.index), pct_lbs.reindex(d.index)], axis=1).mean(axis=1, skipna=True)
    d["R"] = pct_rev.reindex(d.index)
    # recurrence: share of previous 4 same-type expiries with T >= 0.90 (needs T on earlier rows => past only)
    d["Rec"] = np.nan
    for et in ["Weekly", "Monthly"]:
        sub = d[d.expiry_type == et].sort_index()
        hi = (sub["T"] >= 0.90).astype(float).where(sub["T"].notna())
        d.loc[sub.index, "Rec"] = hi.shift(1).rolling(4, min_periods=2).mean()
    d["Rec"] = d["Rec"].fillna(0.0)               # no evidence of recurrence yet
    comp = d[["A", "T", "R", "Rec"]]
    wv = pd.Series(WEIGHTS)
    d["U"] = (comp * wv).sum(axis=1, min_count=1) / (comp.notna() * wv).sum(axis=1)
    gap_term = ((pct_gap.reindex(d.index) - 0.8) / 0.2).clip(0, 1) * 0.6
    d["news_expl"] = np.nanmax(np.vstack([
        m.loc[d.index, "event_on_day"].values * 1.0,
        (m.loc[d.index, "events_pm5d"].fillna(0).values >= 1) * 0.6,
        gap_term.fillna(0).values]), axis=0)
    d["MIRS"] = d["U"] * (1 - LAMBDA * d["news_expl"])
    for c in ["hedge_expl", "liquidity_expl", "rebalance_expl", "arbitrage_expl", "C_concentration", "I_price_impact", "X_cross_market"]:
        d[c] = np.nan                              # explicit: NOT TESTABLE with spot-only data
    d = d.dropna(subset=["U"]).copy()
    d["n_signals"] = ((d["A"] >= SIGNAL_PCT).astype(int) + (d["T"] >= SIGNAL_PCT).astype(int)
                      + (d["R"] >= SIGNAL_PCT).astype(int) + (d["Rec"] >= REC_SIGNAL).astype(int))
    d["tier"] = "Green"
    d.loc[d["n_signals"] >= 1, "tier"] = "Amber"
    d.loc[(d["n_signals"] >= 2) & (d["T"] >= SIGNAL_PCT) & (d["news_expl"] < EXPLAINED), "tier"] = "Orange"
    d["rank_U"] = d["U"].rank(ascending=False, method="min")
    d["rank_MIRS"] = d["MIRS"].rank(ascending=False, method="min")
    ml = ml_df[["pct_IF", "pct_LOF", "pct_SVM"]].copy()
    ml["ml_consensus"] = ml.median(axis=1)
    ml["ml_2of3_above_90"] = ((ml[["pct_IF", "pct_LOF", "pct_SVM"]] >= 0.90).sum(axis=1) >= 2).astype(int)
    d = d.join(ml[["ml_consensus", "ml_2of3_above_90"]], how="left")
    d["label"] = label
    return d


def report(d, label):
    log("\n" + "=" * 74 + f"\nMIRS-lite - {label}  (n = {len(d)} expiries; {d.index.min().date()} to {d.index.max().date()})\n" + "=" * 74)
    log("Tier counts:", d["tier"].value_counts().reindex(["Green", "Amber", "Orange"]).fillna(0).astype(int).to_dict(),
        "| Red: NOT ASSIGNABLE (no cross-market evidence in spot-only data)")
    log("Tier by expiry type:\n" + pd.crosstab(d["expiry_type"], d["tier"]).to_string())
    log("Tier by year:\n" + pd.crosstab(d.index.year, d["tier"]).to_string())
    top = d.nlargest(12, "MIRS")[["expiry_type", "regime", "A", "T", "R", "Rec", "n_signals", "U", "news_expl", "MIRS", "tier", "ml_consensus"]]
    log("\nTop 12 by MIRS:\n" + top.round(2).to_string())
    log("\nNegative controls (listed-event expiries; the explanation term should REDUCE them). NOTE: the discount for these three "
        "is mechanical (listed event on the day), so this shows the mechanism works, not that the discount size is validated:")
    for dt in NEG_CONTROLS:
        ts = pd.Timestamp(dt)
        if ts in d.index:
            r = d.loc[ts]
            log(f"  {dt}: signals={int(r.n_signals)}  U={r.U:.2f} (rank {int(r.rank_U)}/{len(d)}) -> news_expl={r.news_expl:.1f} -> "
                f"MIRS={r.MIRS:.2f} (rank {int(r.rank_MIRS)}) tier={r.tier}")
        else:
            log(f"  {dt}: not in this set")
    # sensitivity: weights
    rng = np.random.RandomState(SEED)
    base = np.array([WEIGHTS[k] for k in ["A", "T", "R", "Rec"]])
    comp = d[["A", "T", "R", "Rec"]]
    top20 = set(d.nlargest(20, "MIRS").index)
    top10 = list(d.nlargest(10, "MIRS").index)
    sp, ov, stay = [], [], {t: 0 for t in top10}
    for _ in range(N_DRAWS):
        wd = rng.dirichlet(base * 20)
        u = (comp * wd).sum(axis=1, min_count=1) / (comp.notna() * wd).sum(axis=1)
        mm = u * (1 - LAMBDA * d["news_expl"])
        sp.append(spearmanr(mm, d["MIRS"])[0])
        tt = set(mm.nlargest(20).index)
        ov.append(len(tt & top20))
        for t in top10:
            stay[t] += int(t in tt)
    log(f"\nWeight sensitivity ({N_DRAWS} Dirichlet draws around the base weights): Spearman vs base: "
        f"median {np.median(sp):.2f}, 5th pct {np.percentile(sp, 5):.2f}; top-20 overlap: mean {np.mean(ov):.1f}/20")
    log("  Share of draws in which each base top-10 expiry stays in the top 20: " +
        ", ".join(f"{t.date()}: {stay[t] / N_DRAWS:.0%}" for t in top10))
    for lam in (0.0, 0.25, 0.75):
        mm = d["U"] * (1 - lam * d["news_expl"])
        log(f"  LAMBDA={lam}: Spearman vs base {spearmanr(mm, d['MIRS'])[0]:.3f}; top-20 overlap {len(set(mm.nlargest(20).index) & top20)}/20")
    # ML sensitivity
    mlv = d.dropna(subset=["ml_consensus"])
    if len(mlv) > 10:
        mm = (0.85 * mlv["U"] + 0.15 * mlv["ml_consensus"]) * (1 - LAMBDA * mlv["news_expl"])
        log(f"\nML-consensus sensitivity (G4 stance: ML is NOT in the base score): Spearman(MIRS, MIRS+15% ML) = "
            f"{spearmanr(mm, mlv['MIRS'])[0]:.2f}; Spearman(MIRS, ML consensus) = {spearmanr(mlv['MIRS'], mlv['ml_consensus'])[0]:.2f}; "
            f"Orange expiries also flagged by >=2 ML models above 0.90: "
            f"{int(((mlv.tier == 'Orange') & (mlv.ml_2of3_above_90 == 1)).sum())}/{int((mlv.tier == 'Orange').sum())}")


# ------------------------------------------------------------------ RUN
rw = pd.read_csv(RES_WF, parse_dates=["date"]).set_index("date")["res_wf_log_r4"]
rr = pd.read_csv(RES_RETRO, parse_dates=["date"]).set_index("date")["res_retro_log_r4"]
mlw = pd.read_csv(ML_WF, index_col=0, parse_dates=True)
mlr = pd.read_csv(ML_RETRO, index_col=0, parse_dates=True)

WF = build(rw.reindex(m.index).dropna(), mlw, "WALK-FORWARD (out-of-sample residual, 2022+)")
RETRO = build(rr.reindex(m.index).dropna(), mlr, "RETROSPECTIVE (residual & ML use future years; descriptive only)")
report(WF, "WALK-FORWARD")
report(RETRO, "RETROSPECTIVE (descriptive; includes 12 Mar 2020)")

WF.to_csv("outputs/step4_mirs_walkforward.csv")
RETRO.to_csv("outputs/step4_mirs_RETROSPECTIVE.csv")
log("\nINTERPRETATION RULE: MIRS ranks SURVEILLANCE PRIORITY only; it is a data-limited upper bound (hedge, liquidity, "
    "rebalance, arbitrage explanations and all cross-market terms are not testable). NOT evidence of manipulation.")
open("outputs/step4_diagnostics.txt", "w").write("\n".join(out))
