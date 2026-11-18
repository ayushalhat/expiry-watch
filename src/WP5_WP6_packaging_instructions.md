# WP5 (partial) and WP6 — packaging instructions

**How this works.** You run the pipeline (Steps 1–5) plus one new script, `wp5_wp6_results.py`, which computes the
remaining WP5/WP6 numbers and bundles *everything the reports need* into `results_package.zip`. You send me that zip (or
the pasted contents listed in Section 5). I then write the WP5 and WP6 documents in the same style as Praneet's WP1/WP2
documents. **Nothing in the reports will be invented: every number will come from your package.**

**Language rule for everything you write or paste:** scores rank *surveillance priority* only. Never "manipulation",
"fraud" or any naming of participants. Regulatory cases are interim allegations, not labels.

---

## 1. Pre-flight checklist (do these BEFORE the results script)

| # | Check | Why it matters for the reports |
|---|---|---|
| 1 | **Step 3: revert the LOF training line** to `res["LOF"] = (-clf.negative_outlier_factor_, -clf.score_samples(Xte))`, then re-run Step 3 | The in-sample version biases test percentiles upward (+0.03 in my calibration test); WP6 must describe the unbiased one |
| 2 | **Re-run Step 4, then Step 5**, in that order (Step 4 reads Step 3's ML columns; Step 5 reads Step 4) | Otherwise the package mixes outputs from different runs |
| 3 | **Install SHAP and re-run Step 2**: `pip install shap`, then `python src/step2_residual_model.py`. Confirm `outputs/expiry_shap.csv` exists | WP6's explainability claim for the residual model depends on SHAP; without it the report can only cite permutation importance |
| 4 | Create `outputs/CHANGES.txt`: one line per edit you made to any of my scripts (e.g. "Step 3: MIN_TRAIN_ROWS 90 -> 80 so Version B scores 2024"; "Step 3: test jitter removed") | The report must disclose post-hoc settings. Include the date of each edit if you remember |
| 5 | Confirm the files exist: `outputs/expiry_features.parquet`, `data/ExpiryWatch_NIFTY_WP1_WP2.xlsx`, `outputs/step2_summary.txt`, `outputs/expiry_residuals_walkforward.csv`, `outputs/expiry_residuals_RETROSPECTIVE_uses_future_years.csv`, `outputs/step3v2_scores_A.csv`, `outputs/step3v2_scores_B.csv`, `outputs/step3v2_scores_RETROSPECTIVE_in_sample.csv`, `outputs/step4_mirs_walkforward.csv`, `outputs/step4_mirs_RETROSPECTIVE.csv`, `outputs/forensics/evidence_packs.md` | The results script copies these into the package and lists any that are missing |

## 2. Run order (from the project root)
```
python src/step2_residual_model.py        # needs shap installed (check 3)
python src/step3_unsupervised_v2.py       # with the LOF line reverted (check 1)
python src/step4_mirs_lite.py
python src/step5_forensics.py
python src/wp5_wp6_results.py             # NEW: computes WP5/WP6 results and builds results_package.zip
```
If any script stops, paste the error and I will fix it — do not edit the numbers by hand.

## 3. What the new script computes, and where it goes in the reports

**WP5 (partial) — cross-market price-influence diagnostics, spot-only subset** (`results_package/WP5/`)

| File | Proposal diagnostic | What it answers |
|---|---|---|
| `wp5_1_settlement_timing_by_group.csv` | Settlement-timing concentration | Final-15-min |return|, range and last-bar share: expiry minus matched controls, for All / Weekly / Monthly / era 2019–2022 vs 2023–2026 and their combinations (mean, relative %, median, share above controls, t, Wilcoxon, BH q within table) |
| `wp5_2_effect_concentration.csv` | Concentration (of the *effect over time*, not constituents) | How much of the total excess final-bar activity comes from the top 5/10/20% of expiries |
| `wp5_3_strike_alignment.csv` | Strike / payoff alignment (**unweighted by OI**) | Mean distance to the nearest 50/100-pt strike and share of closes within 0.05 of a strike, vs the no-pinning expectation; also for the top-20 MIRS expiries |
| `wp5_4_reversal_conditional.csv` | Reversal | Next-day signed reversal (expiry minus controls), overall and conditional on a large final-bar move, on no listed event, on high T |
| `wp5_5_recurrence_serial_dependence.csv`, `wp5_5b_quarter_end_monthlies.csv`, `wp5_5c_top_decile_by_year.csv` | Recurrence | Lag-1 autocorrelation and clustering of top-decile expiries (permutation tests), quarter-end months, year profile |

**WP6 — AI/ML anomaly detection** (`results_package/WP6/` plus `from_steps/`)

| File | What it supports in the report |
|---|---|
| `from_steps/step2_summary.txt`, `step2_importance.csv`, `step2_expiry_shap.csv` | Gradient-boosted residual ("expected late-session move") model: out-of-sample R², expiry-minus-non-expiry difference (all/weekly/monthly), feature importance, SHAP |
| `wp6_1_model_agreement.csv` | Spearman agreement between Isolation Forest, LOF, One-Class SVM with bootstrap CIs |
| `wp6_2_consensus_vs_chance.csv` | Whether expiries flagged by ≥2 of 3 models exceed what independence gives (permutation) |
| `wp6_3_consensus_profile.csv` | Whether consensus-flagged expiries differ in residual / EVR; **gate G4** correlation with the residual |
| `wp6_4_tier_cutoff_sensitivity.csv`, `wp6_5_top20_mirs_walkforward.csv` | Tier counts vs the 0.80–0.95 signal cut-off; the top-20 MIRS table |
| `from_steps/step3v2_diagnostics.txt`, `step4_diagnostics.txt`, `step4_mirs_*.csv` | Stability tests, weight/λ/ML sensitivity, negative controls, tiers |
| `from_steps/forensics/` | The 17 draft evidence cards and charts |

## 4. Reference values (check your run against these; WP5 should match exactly, WP6 approximately)
These come from my reconstruction of your tables (same raw data; parquet and WP2 join values were verified identical).

**WP5 — expected to match exactly:** 367 expiries (282 weekly, 85 monthly); 0 NaN in the WP2 difference columns.
- All: |r4| diff +1.48 bps (+19%), range diff +1.88 bps (+12%). Weekly: +0.53 bps (+7%, p≈0.33), +0.36 bps (+2%). Monthly: +4.62 bps (+60%), +6.91 bps (+45%), p<0.001.
- Era 2019–2022: |r4| diff −0.13 bps (p≈0.87); era 2023–2026: +3.02 bps (+50%), p<0.001.
- Concentration: top 10% of expiries (37) contribute ≈53% of total positive excess |r4|.
- Strike: all-expiry mean distance 0.244 (50-pt) and 0.259 (100-pt); share within 0.05 of a 50-pt strike 11.4% vs 10% expected (p≈0.34).
- Recurrence: no significant lag-1 autocorrelation; one nominal hit (last-bar-share top-decile pairs, weekly: 7 vs 2.8 expected, p=0.014, BH q≈0.09 → **not** significant after correction).

**WP6.4 — expected to match exactly (depends on Steps 2 and 4 only):** Orange / Amber / Green = 14/111/114 at 0.80; 7/95/137 at 0.85; **2/64/173 at 0.90**; 1/34/204 at 0.95. Six of the top-20 MIRS are Green.
**WP6.1–6.3 — approximate (they depend on Step 3, which you changed):** model correlations near +0.06 / −0.02 / +0.22 (IF–LOF / IF–SVM / LOF–SVM); ≥2-of-3 above 0.90: ≈18 observed vs ≈10.8 expected under independence (permutation p≈0.005); gate G4 ρ ≈ 0.11–0.14.

If a WP5 number differs, a data or join problem exists — send me the line that differs before sending anything else.

## 5. What to send me
**Preferred:** `results_package.zip` (everything below is inside it). If you cannot upload the zip, paste:
1. `results_package/RESULTS_SUMMARY.txt` (complete);
2. `outputs/step2_summary.txt`, `outputs/step3v2_diagnostics.txt`, `outputs/step4_diagnostics.txt`;
3. the top 15 rows of `outputs/importance.csv` and a yes/no: does `outputs/expiry_shap.csv` exist?;
4. `outputs/CHANGES.txt`;
5. `outputs/forensics/forensics_summary.csv`.

**Also tell me (one line each):**
- Report format wanted (Word/PDF/Markdown) and length limits; whether to mimic Praneet's PDF layout.
- Author names and course/instructor line for the title page.
- Whether WP5/WP6 are separate documents or sections of the main report.
- Anything in the instructor's brief that says what WP5/WP6 must contain.

## 6. What I will write from the package
**WP5 (partial): "Cross-Market Price-Influence Diagnostics — spot-only subset".** Purpose and scope → inputs → the
diagnostics that could be built (5.1–5.5) with results → a requirements table (below) → limitations → implications for later
work and data needed → appendix (definitions, file map).

| Proposal diagnostic | Status | Reason | Data needed |
|---|---|---|---|
| Settlement-timing concentration | Built (2-hour bars: final 15 min only) | Final 30/5 min and the VWAP window cannot be isolated | Minute bars |
| Index-contribution concentration (WPPI, EIC) | **Not built** | No constituent data | NIFTY 50 constituent prices and weights |
| Price impact (Kyle λ) | **Not built** | No signed order flow or volume | Order/trade data (Tier B) |
| Cross-market asymmetry (CMBR) | **Not built** | No option OI, futures or participant data | F&O bhavcopy; participant data for full version |
| Strike / payoff alignment | Built, **unweighted** | No OI by strike | F&O bhavcopy |
| Reversal | Built (next-day only) | No intraday post-expiry bars | Minute bars; WP7 news conditioning |
| Recurrence | Built (NIFTY only) | No other indices | Bank Nifty / Sensex / FINNIFTY 2-hour bars |

**WP6: "AI/ML Anomaly Detection — spot-only prototype".** Design principles (unsupervised, walk-forward, explanation-first) →
Model 1: gradient-boosted residual model (results, SHAP) → Model 2: Isolation Forest / LOF / One-Class SVM (features, one-sided
past-only percentile ranks, fold-comparable scores, agreement, consensus, stability) → gate G4 → MIRS-lite (components, news
discount, tiers, sensitivity, negative controls) → forensics cards → limitations → methods not built (autoencoder, HDBSCAN,
change-point) and why → appendix.

## 7. Caveats I will state in the reports (so you are not surprised)
1. The three unsupervised models agree weakly (ρ ≈ −0.03 to 0.22); only the consensus above the 90th percentile exceeds chance, and the consensus group's higher residual/EVR is **partly circular** (shared inputs).
2. Gate G4 is **not passed**: the ML ranking has not shown stable out-of-sample value beyond the econometric residual, so it is excluded from the base MIRS.
3. **Tier membership depends on the cut-off** (Orange 14 → 1 as the cut-off goes 0.80 → 0.95); rankings, not tiers, are the primary output. Only 12 Sep 2024 stays Orange across cut-offs ≥ 0.85.
4. The **news discount is a fixed rule**, not validated; WP7 is needed. The negative-control improvement is mechanical.
5. **Red is not assignable**: no cross-market evidence exists in spot-only data. MIRS-lite is an upper bound because hedge, liquidity, rebalance and arbitrage explanations are missing.
6. WP2/WP5 matching uses controls up to ±60 calendar days after an expiry and full-sample standardisation (mild look-ahead, inherited from WP1).
7. The **era effect (2019–22 vs 2023–26) is descriptive** and confounded with regime changes, lot sizes, STT hikes and the monthly share; it is not a causal reform estimate (that is WP8).
8. Strike analysis is unweighted by open interest and uses the 15:30 spot close, not the settlement VWAP.
9. All p-values are exploratory; BH q-values are within-table only. Weekly expiries are serially correlated, so naive t-tests overstate precision.
10. Settings changed after seeing results (disclosed from `CHANGES.txt`): at least `MIN_TRAIN_ROWS` (90→80), test jitter removal.
11. The CAS sample (9 expiries) is excluded from all WP5/WP6 results (S1 only).
12. The two zero-return final bars are floored at 1 bp in the log target.
