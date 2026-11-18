"""
verify_step3.py - prints the facts needed to reconcile two runs of Step 3 (read-only; changes nothing).

Run from the project root AFTER step3_unsupervised_v2.py (your edited copy) has run:
    python src/verify_step3.py  [path/to/your_step3_script.py]

Paste the COMPLETE output back. If a section errors, paste the error too.
"""
import re, sys, platform
import numpy as np, pandas as pd
from scipy.stats import spearmanr

SCRIPT = sys.argv[1] if len(sys.argv) > 1 else "src/step3_unsupervised_v2.py"
H = lambda t: print("\n" + "=" * 70 + f"\n{t}\n" + "=" * 70)

H("Q1  ENVIRONMENT")
import sklearn, scipy
print("python", platform.python_version(), "| numpy", np.__version__, "| pandas", pd.__version__,
      "| sklearn", sklearn.__version__, "| scipy", scipy.__version__)

H("Q2  CONFIG + MODEL CODE AS IT ACTUALLY IS IN YOUR SCRIPT (to see the 'LOF fix' and any edited constants)")
try:
    src = open(SCRIPT, encoding="utf-8").read()
    for pat in [r"^WF_SCORE_FROM.*", r"^MIN_PAST_FOR_RANK.*", r"^MIN_TRAIN_ROWS.*", r"^SEED.*", r"^BASE\s*=.*",
                r"^BEHAVIOUR.*", r"^NEG_CONTROLS.*"]:
        for line in re.findall(pat, src, flags=re.M):
            print(line)
    i = src.find("def fold_scores")
    j = src.find("def to_pct")
    print("\n--- fold_scores() as in your file ---")
    print(src[i:j] if i >= 0 else "fold_scores not found")
    k = src.find("def one_sided")
    print("--- one_sided() ---")
    print(src[k:k + 400] if k >= 0 else "one_sided not found")
except Exception as ex:
    print("could not read script:", ex)

H("Q3  expiry_features.parquet SANITY")
e = pd.read_parquet("outputs/expiry_features.parquet")
print("index name:", e.index.name, "| index dtype:", e.index.dtype, "| rows:", len(e),
      "| index unique:", e.index.is_unique, "| sorted:", e.index.is_monotonic_increasing)
print("columns:", e.columns.tolist())
mo = e[e["model_ok"]].copy()
mo.index = pd.to_datetime(mo.index)
print("model_ok rows:", len(mo))
for c in ["evr", "reversal_ratio", "r4", "overnight_gap", "events_pm5d", "lbs"]:
    if c in mo.columns:
        s = pd.to_numeric(mo[c], errors="coerce")
        print(f"{c:15s} n={s.notna().sum():3d} NaN={s.isna().sum():3d} mean={s.mean():+.5f} "
              f"median={s.median():+.5f} min={s.min():+.5f} max={s.max():+.5f}")
print("overnight_gap negative share (signed if ~0.4-0.5):", round((mo["overnight_gap"] < 0).mean(), 2))
print("r4 negative share (signed if ~0.4-0.5):", round((mo["r4"] < 0).mean(), 2))
print("events_pm5d value counts:", mo["events_pm5d"].value_counts().sort_index().to_dict())

H("Q4  WP2 DIFFERENCE COLUMNS joined onto the 367 (expected from the WP2 document: ~ +0.00015, +0.00019, +0.020)")
raw = pd.read_excel("data/ExpiryWatch_NIFTY_WP1_WP2.xlsx", sheet_name="WP2 Expiry vs Control", header=None)
w = raw.iloc[2:].copy()
w["date"] = pd.to_datetime(w[1])
w = w.set_index("date")
for name, col in [("r4_diff", 32), ("range4_diff", 35), ("lbs_diff", 38)]:
    s = pd.to_numeric(w.loc[w.index.isin(mo.index), col], errors="coerce")
    print(f"{name:12s} n={s.notna().sum()} NaN={s.isna().sum()} mean={s.mean():+.6f} median={s.median():+.6f}")

H("Q5  STEP 3 OUTPUT FILES")
A = pd.read_csv("outputs/step3v2_scores_A.csv", index_col=0, parse_dates=True)
B = pd.read_csv("outputs/step3v2_scores_B.csv", index_col=0, parse_dates=True)
Rt = pd.read_csv("outputs/step3v2_scores_RETROSPECTIVE_in_sample.csv", index_col=0, parse_dates=True)
for nm, d in [("A", A), ("B", B), ("RETRO", Rt)]:
    print(f"\n[{nm}] rows={len(d)}  per-year counts: {d.groupby(d.index.year).size().to_dict()}")
    if len(d) > 5:
        print("  Spearman IF-LOF %.3f | IF-SVM %.3f | LOF-SVM %.3f" % (
            spearmanr(d.pct_IF, d.pct_LOF)[0], spearmanr(d.pct_IF, d.pct_SVM)[0], spearmanr(d.pct_LOF, d.pct_SVM)[0]))
        print("  pct_* column means (should be ~0.5):", d[["pct_IF", "pct_LOF", "pct_SVM"]].mean().round(3).to_dict())
        k = (d[["pct_IF", "pct_LOF", "pct_SVM"]] >= 0.90).sum(axis=1)
        print("  expiries with >=2 models above 0.90:", int((k >= 2).sum()), "| all 3:", int((k == 3).sum()))
print("\nRETRO top 10 (date, type, pcts):")
print(Rt.nlargest(10, "avg_pct")[["expiry_type", "pct_IF", "pct_LOF", "pct_SVM", "avg_pct"]].round(3).to_string())
print("\nNegative controls in RETRO (rank of n):")
for dt in ["2020-03-12", "2023-01-25", "2024-02-01"]:
    t = pd.Timestamp(dt)
    print(dt, int(Rt.loc[t, "priority_rank"]) if t in Rt.index else "absent", "of", len(Rt))
print("\nA top 8:")
print(A.nlargest(8, "avg_pct")[["expiry_type", "pct_IF", "pct_LOF", "pct_SVM", "avg_pct"]].round(3).to_string())

H("Q6  GATE G4 + STABILITY blocks exactly as your run printed them")
try:
    txt = open("outputs/step3v2_diagnostics.txt", encoding="utf-8").read()
    for key in ["GATE G4", "STABILITY", "NaN counts", "Rank matrix", "State-contamination"]:
        for m_ in re.finditer(key, txt):
            print(txt[max(0, m_.start() - 5): m_.start() + 700].split("\n\n")[0])
            print("-----")
            break
except Exception as ex:
    print("diagnostics file missing:", ex)
