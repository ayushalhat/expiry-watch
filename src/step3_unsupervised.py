"""
Step 3 (v2) - Unsupervised anomaly ranking of NIFTY expiries.  ExpiryWatch India, spot-only (Tier A).

What changed vs v1 (and why)
  1. Anomaly INPUTS are expiry-day BEHAVIOUR only (EVR, final-bar vs controls, last-bar share vs controls,
     reversal). Market STATE / news variables (rv20, r5, gap, event count) are kept as annotations for the
     explanation term of MIRS, NOT as model inputs: otherwise a calm-vs-stormy market is flagged, not odd behaviour.
  2. ONE-SIDED: surveillance cares about unusually ACTIVE closes, not unusually quiet ones. Percentile ranks are
     clipped at the median, so a very quiet expiry is "normal", not an outlier.
  3. Scores are made COMPARABLE ACROSS FOLDS: each fold's test scores are converted to a percentile of that
     fold's own training-score distribution (v1 pooled raw scores from different models).
  4. Version B no longer pretends to score 2022+: with a min-history rule it can only score 2024+. Stated honestly.
  5. A RETROSPECTIVE in-sample run (clearly labelled) lets the 12 Mar 2020 negative control be inspected,
     because 2019-2021 is burn-in in the walk-forward.
  6. G4 test: does the ML ranking carry information beyond the Step 2 residual?  (Version A vs residual.)
  7. Stability check across hyper-parameters / seeds (proposal: results must be stable).
  8. Fixes: WP2 columns coerced to numeric; "scaled matrix" file now really saves the scaled ranks;
     unused retrospective-residual load removed; degenerate ranks from tiny histories excluded.

Run from project root:  python src/step3_unsupervised_v2.py
INTERPRETATION RULE: scores rank SURVEILLANCE PRIORITY only. They are NOT evidence of manipulation.
"""
import warnings
import numpy as np
import pandas as pd
from scipy.stats import spearmanr
from sklearn.ensemble import IsolationForest
from sklearn.neighbors import LocalOutlierFactor
from sklearn.svm import OneClassSVM
from sklearn.preprocessing import RobustScaler

warnings.filterwarnings("ignore")

# ------------------------------------------------------------------ CONFIG
EXPIRY_PARQ = "outputs/expiry_features.parquet"
WP2_XLSX = "data/ExpiryWatch_NIFTY_WP1_WP2.xlsx"
RESID_WF = "outputs/expiry_residuals_walkforward.csv"      # Step 2 output (2022+, out-of-sample)

WF_SCORE_FROM = 2022
MIN_PAST_FOR_RANK = 10          # a rank vs fewer than 10 past same-type expiries is meaningless -> NaN
MIN_TRAIN_ROWS = 80             # minimum training rows to fit a fold
NEG_CONTROLS = ["2020-03-12", "2023-01-25", "2024-02-01"]
SEED = 42

BEHAVIOUR = ["evr", "r4_diff", "range4_diff", "lbs_diff", "reversal_ratio"]
ORIGINAL_V1 = ["evr", "r4_abs", "r4_diff", "range4_diff", "lbs", "lbs_diff", "overnight_gap", "rv20",
               "r5", "events_pm5d", "reversal_ratio", "has_reversal", "strike50"]   # for comparison only
ANNOTATIONS = ["rv20", "r5", "overnight_gap", "events_pm5d", "strike50"]

BASE = dict(if_n=200, if_seed=SEED, lof_k=15, svm_nu=0.10)
out = []


def log(*a):
    s = " ".join(str(x) for x in a)
    print(s)
    out.append(s)


# ------------------------------------------------------------------ 1. LOAD
log("=" * 72 + "\nStep 3 v2 - unsupervised anomaly ranking (ExpiryWatch India)\n" + "=" * 72)
e = pd.read_parquet(EXPIRY_PARQ)
e.index = pd.to_datetime(e.index)
e = e[e["model_ok"]].copy()
assert len(e) == 367, f"expected 367 model_ok expiries, got {len(e)}"
log(f"model_ok expiries: {len(e)}")

raw = pd.read_excel(WP2_XLSX, sheet_name="WP2 Expiry vs Control", header=None)
wp2 = raw.iloc[2:].copy()                    # two header rows
wp2.columns = range(wp2.shape[1])
wp2["date"] = pd.to_datetime(wp2[1])
# 0-indexed positions verified against the sheet: 32 = |final-15-min return| diff, 35 = final-15-min range diff,
# 38 = last-bar share diff
wp2 = wp2[["date", 32, 35, 38]].rename(columns={32: "r4_diff", 35: "range4_diff", 38: "lbs_diff"})
for c in ["r4_diff", "range4_diff", "lbs_diff"]:
    wp2[c] = pd.to_numeric(wp2[c], errors="coerce")
wp2 = wp2.set_index("date")

resid = pd.read_csv(RESID_WF, parse_dates=["date"]).set_index("date")[["z_wf_log_r4"]] \
    .rename(columns={"z_wf_log_r4": "resid_z"})
res_raw = pd.read_csv(RESID_WF, parse_dates=["date"]).set_index("date")
log(f"Step 2 walk-forward residuals: {len(resid)} rows")

m = e[["expiry_type", "regime", "evr", "r4", "lbs", "overnight_gap", "rv20", "r5", "events_pm5d",
       "reversal_ratio"]].copy()
m["r4_abs"] = m["r4"].abs()
m = m.join(wp2, how="left").join(resid, how="left")
m["strike50"] = (e["close"] % 50).pipe(lambda s: np.minimum(s, 50 - s)) / 50
m["has_reversal"] = m["reversal_ratio"].notna().astype(float)
m["year"] = m.index.year
log("NaN counts:", m.isna().sum()[m.isna().sum() > 0].to_dict())

# ------------------------------------------------- 2. PAST-ONLY PERCENTILE RANKS (per expiry type)
RANK_COLS = sorted(set(BEHAVIOUR + ORIGINAL_V1 + ["resid_z"]) - {"has_reversal"} | {"has_reversal"})
ranks = pd.DataFrame(np.nan, index=m.index, columns=RANK_COLS)
for et in ["Weekly", "Monthly"]:
    idx = m.index[m.expiry_type == et].sort_values()
    for i, dt in enumerate(idx):
        if i < MIN_PAST_FOR_RANK:
            continue
        past = m.loc[idx[:i], RANK_COLS]
        for c in RANK_COLS:
            v = m.at[dt, c]
            pv = past[c].dropna()
            if pd.isna(v) or len(pv) < MIN_PAST_FOR_RANK:
                continue
            ranks.at[dt, c] = (pv < v).mean() + 0.5 * (pv == v).mean()      # mid-rank, past-only
ranks["reversal_ratio"] = ranks["reversal_ratio"].where(m["reversal_ratio"].notna(), 0.5)  # blank = neutral
ranks.to_csv("outputs/step3v2_scaled_rank_matrix.csv")
log(f"Rank matrix {ranks.shape}; rows with a complete BEHAVIOUR vector: {ranks[BEHAVIOUR].dropna().shape[0]}")


def one_sided(X):
    """Clip at the median and rescale: only the UPPER tail (unusually active) can look anomalous."""
    return np.maximum(X - 0.5, 0.0) * 2.0


# ------------------------------------------------- 3. MODELS (each returns train & test anomaly scores)
def fold_scores(Xtr, Xte, P):
    rng = np.random.RandomState(SEED)
    Xtr = Xtr + rng.normal(0, 1e-3, Xtr.shape)       # jitter train only: clipping creates many identical rows (breaks LOF)
    # Xte is NOT jittered — test scores must be deterministic and comparable across runs
    res = {}
    clf = IsolationForest(n_estimators=P["if_n"], random_state=P["if_seed"]).fit(Xtr)
    res["IF"] = (-clf.score_samples(Xtr), -clf.score_samples(Xte))
    clf = LocalOutlierFactor(n_neighbors=P["lof_k"], novelty=True).fit(Xtr)
    # Training reference: negative_outlier_factor_ uses leave-one-out LOF, which is the correct
    # calibrated reference for to_pct (avg test percentile ~0.496).
    # score_samples(Xtr) is in-sample (each point sees itself as neighbour), producing a biased
    # reference that inflates test percentiles by ~+0.03. Do NOT use score_samples on Xtr here.
    res["LOF"] = (-clf.negative_outlier_factor_, -clf.score_samples(Xte))
    sc = RobustScaler().fit(Xtr)
    clf = OneClassSVM(kernel="rbf", nu=P["svm_nu"], gamma="scale").fit(sc.transform(Xtr))
    res["SVM"] = (-clf.decision_function(sc.transform(Xtr)), -clf.decision_function(sc.transform(Xte)))
    return res


def to_pct(tr, te):
    return (tr[None, :] < te[:, None]).mean(axis=1)          # share of training scores below the test score


def walk_forward(feats, P=BASE, subset=None, label=""):
    R = ranks[feats].copy()
    if subset is not None:
        R = R.loc[subset]
    R = R.dropna()
    meta = m.loc[R.index]
    parts = []
    for yr in range(WF_SCORE_FROM, int(meta.year.max()) + 1):
        tr_idx = meta.index[meta.year < yr]
        te_idx = meta.index[meta.year == yr]
        if len(te_idx) == 0:
            continue
        if len(tr_idx) < MIN_TRAIN_ROWS:
            log(f"  [{label}] {yr}: skipped (only {len(tr_idx)} training rows, need {MIN_TRAIN_ROWS})")
            continue
        fs = fold_scores(one_sided(R.loc[tr_idx].values), one_sided(R.loc[te_idx].values), P)
        d = pd.DataFrame({f"pct_{k}": to_pct(*v) for k, v in fs.items()}, index=te_idx)
        parts.append(d)
        log(f"  [{label}] {yr}: scored {len(te_idx)} expiries (train rows {len(tr_idx)})")
    if not parts:
        return pd.DataFrame()
    s = pd.concat(parts)
    s["avg_pct"] = s[["pct_IF", "pct_LOF", "pct_SVM"]].mean(axis=1)
    s["priority_rank"] = s["avg_pct"].rank(ascending=False, method="min")     # 1 = highest surveillance priority
    return s.join(m[["expiry_type", "regime"]])


# ------------------------------------------------- 4. RUN
log("\n" + "=" * 72 + "\nVERSION A - behaviour features only (no Step 2 residual)\n" + "=" * 72)
log("Features:", BEHAVIOUR)
A = walk_forward(BEHAVIOUR, label="A")

log("\n" + "=" * 72 + "\nVERSION B - behaviour + Step 2 walk-forward residual (burn-in 2022-2023, scored 2024+)\n" + "=" * 72)
B_feats = BEHAVIOUR + ["resid_z"]
B = walk_forward(B_feats, subset=m.index[m["resid_z"].notna()], label="B")

log("\n" + "=" * 72 + "\nCOMPARISON - v1 original 13 features (state + behaviour), same walk-forward, one-sided\n" + "=" * 72)
A_old = walk_forward([c for c in ORIGINAL_V1], label="A_orig")


# ------------------------------------------------- 5. RETROSPECTIVE (in-sample) for burn-in negative controls
log("\n" + "=" * 72 + "\nRETROSPECTIVE in-sample run (ALL years; descriptive only, NOT out-of-sample)\n" + "=" * 72)
R = ranks[BEHAVIOUR].dropna()
fs = fold_scores(one_sided(R.values), one_sided(R.values), BASE)
retro = pd.DataFrame({f"pct_{k}": to_pct(v[0], v[0]) for k, v in fs.items()}, index=R.index)
retro["avg_pct"] = retro.mean(axis=1)
retro["priority_rank"] = retro["avg_pct"].rank(ascending=False, method="min")
retro = retro.join(m[["expiry_type", "regime"]])


# ------------------------------------------------- 6. DIAGNOSTICS
def diag(s, label):
    if s.empty:
        log(f"[{label}] nothing scored")
        return
    log(f"\n[{label}] n scored = {len(s)}")
    pairs = [("pct_IF", "pct_LOF"), ("pct_IF", "pct_SVM"), ("pct_LOF", "pct_SVM")]
    for a, b in pairs:
        rho = spearmanr(s[a], s[b])[0]
        t = {c: set(s.nlargest(20, c).index) for c in (a, b)}
        j = len(t[a] & t[b]) / len(t[a] | t[b])
        log(f"  {a[4:]} vs {b[4:]}: Spearman {rho:.2f} | top-20 Jaccard {j:.2f}")
    top = s.nlargest(20, "avg_pct")
    vc = top.expiry_type.value_counts()
    log(f"  Top-20 by avg percentile: Weekly {vc.get('Weekly', 0)}, Monthly {vc.get('Monthly', 0)}  "
        f"(base rates in scored set: weekly {np.mean(s.expiry_type == 'Weekly'):.0%})")
    for dt in NEG_CONTROLS:
        ts = pd.Timestamp(dt)
        if ts in s.index:
            log(f"  Negative control {dt}: priority rank {int(s.loc[ts, 'priority_rank'])} of {len(s)} "
                f"(avg percentile {s.loc[ts, 'avg_pct']:.2f})")
        else:
            log(f"  Negative control {dt}: not in this scored set")


diag(A, "Version A (walk-forward)")
diag(B, "Version B (walk-forward, 2024+)")
diag(A_old, "v1-style 13 features (walk-forward)")
diag(retro, "RETROSPECTIVE in-sample")

# --- state-variable contamination check: do the original (state-inclusive) features simply flag stormy markets?
if not A.empty and not A_old.empty:
    j = A.join(A_old[["avg_pct"]], rsuffix="_orig", how="inner").join(m[["rv20"]])
    log(f"\nState-contamination check (A vs v1-style): Spearman(avg_pct_A, avg_pct_v1) = "
        f"{spearmanr(j.avg_pct, j.avg_pct_orig)[0]:.2f}; "
        f"Spearman(rv20, v1 score) = {spearmanr(j.rv20, j.avg_pct_orig)[0]:.2f} vs "
        f"Spearman(rv20, A score) = {spearmanr(j.rv20, j.avg_pct)[0]:.2f}")

# --- G4: does ML add information beyond the Step 2 econometric residual?
log("\n" + "=" * 72 + "\nGATE G4 - does the ML ranking add anything beyond the Step 2 residual? (Version A vs residual)\n" + "=" * 72)
g = A.join(res_raw[["res_wf_log_r4", "z_wf_log_r4"]], how="inner")
if len(g):
    rho = spearmanr(g.avg_pct, g.res_wf_log_r4)[0]
    t_ml = set(g.nlargest(20, "avg_pct").index)
    t_rs = set(g.nlargest(20, "res_wf_log_r4").index)
    log(f"n = {len(g)}; Spearman(ML avg percentile, residual) = {rho:.2f}; top-20 overlap {len(t_ml & t_rs)}/20")
    log("Reading: high correlation + high overlap => ML mostly re-discovers the residual (adds little);"
        " moderate => complementary (EVR/reversal/lbs dimensions); low => check features.")

# ------------------------------------------------- 7. STABILITY (hyper-parameters / seeds)
log("\n" + "=" * 72 + "\nSTABILITY - Version A, Spearman of avg percentile vs default settings\n" + "=" * 72)
if not A.empty:
    variants = {
        "IF 100 trees, seed 1": {**BASE, "if_n": 100, "if_seed": 1},
        "IF 400 trees, seed 2": {**BASE, "if_n": 400, "if_seed": 2},
        "LOF k=10": {**BASE, "lof_k": 10},
        "LOF k=25": {**BASE, "lof_k": 25},
        "SVM nu=0.05": {**BASE, "svm_nu": 0.05},
        "SVM nu=0.20": {**BASE, "svm_nu": 0.20},
    }
    import io, contextlib
    for name, P in variants.items():
        with contextlib.redirect_stdout(io.StringIO()):
            V = walk_forward(BEHAVIOUR, P=P, label="stab")
        common = A.index.intersection(V.index)
        top_d = set(A.loc[common].nlargest(20, "avg_pct").index)
        top_v = set(V.loc[common].nlargest(20, "avg_pct").index)
        log(f"  {name:22s} Spearman {spearmanr(A.loc[common, 'avg_pct'], V.loc[common, 'avg_pct'])[0]:.2f} | "
            f"top-20 overlap {len(top_d & top_v)}/20")

# ------------------------------------------------- 8. TOP LISTS + SAVE
def show_top(s, label, n=15):
    if s.empty:
        return
    cols = ["expiry_type", "regime", "pct_IF", "pct_LOF", "pct_SVM", "avg_pct", "priority_rank"]
    log(f"\nTop {n} - {label}:")
    log(s.nlargest(n, "avg_pct")[cols].round(3).to_string())


show_top(A, "Version A (walk-forward, 2022+)")
show_top(B, "Version B (walk-forward, 2024+)")
A.to_csv("outputs/step3v2_scores_A.csv")
B.to_csv("outputs/step3v2_scores_B.csv")
retro.to_csv("outputs/step3v2_scores_RETROSPECTIVE_in_sample.csv")
log("\nINTERPRETATION RULE: scores rank SURVEILLANCE PRIORITY only; high = unusually active close/behaviour relative to "
    "past expiries of the same type. NOT evidence of manipulation or any legal violation.")
open("outputs/step3v2_diagnostics.txt", "w").write("\n".join(out))