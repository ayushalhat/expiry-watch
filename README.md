# ExpiryWatch: Indian Derivatives Settlement Surveillance & Anomaly Analytics

ExpiryWatch is a quantitative analytics and market surveillance framework designed to analyze settlement-window dynamics, price behavior, and potential anomalies in Indian equity index derivatives (NIFTY 50).

---

## Repository Structure

```text
expiry-watch/
├── RQs/                       # Econometric Research Questions (RQ5, RQ6, RQ8)
│   ├── RQ5/                  # Settlement window price distortion & reversal analysis
│   ├── RQ6/                  # Anomaly recurrence, serial dependence & clustering
│   ├── RQ8/                  # 2024–2026 derivatives reform impacts & relocation
│   ├── packages/             # Original bundled zip packages
│   └── README.md             # Detailed guide and reproduction steps for RQs
├── data/                     # Primary datasets and benchmark databases
│   ├── ExpiryWatch_NIFTY_WP1_WP2.xlsx
│   └── NIFTY_2h_OHLC_data.csv
├── outputs/                  # Model outputs, feature matrices, residuals, forensics
│   ├── forensics/            # Evidence packs, event plots, forensics summary
│   ├── daily_features.parquet
│   ├── expiry_features.parquet
│   ├── expiry_residuals.csv
│   └── ...
├── reports/                  # LaTeX sources, generated figures, and compiled PDF reports
│   ├── RQ5_report_section_v2.pdf
│   ├── RQ6_report_section_v2.pdf
│   ├── RQ8_report_section_v2.pdf
│   ├── WP5_Cross_Market_Diagnostics.tex
│   ├── WP6_AI_ML_Anomaly_Detection.tex
│   ├── WP7_Implementation_Review.md
│   └── build_reports.py
├── results_package/          # Packaged deliverables for Work Packages WP5–WP8
│   ├── WP5/                  # Cross-market & settlement diagnostics
│   ├── WP6/                  # Machine learning consensus & sensitivity
│   ├── WP7/                  # News evidence catalog & review
│   ├── WP8/                  # Interactive dashboard application
│   └── RESULTS_SUMMARY.txt
├── src/                      # Source pipeline & analytical scripts
│   ├── build_features.py     # Feature engineering from OHLC data
│   ├── step2_residual_model.py # Residual model & baseline scoring
│   ├── step3_unsupervised.py # Unsupervised anomaly detection (IF, LOF, SVM)
│   ├── step4_mirs_lite.py    # Multi-Indicator Ranking Score (MIRS-lite)
│   ├── step5_forensics.py    # Event-level forensics & visualization
│   ├── step6_wp7_news.py     # News validation & catalog audit
│   ├── step7_dashboard.py    # Streamlit interactive surveillance dashboard
│   └── wp5_wp6_results.py    # Work package diagnostic generation
└── results_package.zip       # Complete pre-packaged results
```

---

## Research Questions (RQs) Summary

For in-depth documentation, tables, figures, and execution details, refer to the [**RQs Documentation**](file:///c:/Users/sawan/Downloads/Finance_project/expiry-watch/RQs/README.md):

- **[RQ5: Settlement Price Distortion & Next-Open Reversal](file:///c:/Users/sawan/Downloads/Finance_project/expiry-watch/RQs/RQ5/RQ5_report_section_v2.pdf)**
  - *Hypothesis*: Do late-session price moves on expiry days reflect transient price pressure that rapidly reverses at the next open?
  - *Finding*: No systematic reversal. Next-day opening price changes show mild continuation rather than transitory manipulation.
- **[RQ6: Anomaly Signature Recurrence & Temporal Clustering](file:///c:/Users/sawan/Downloads/Finance_project/expiry-watch/RQs/RQ6/RQ6_report_section_v2.pdf)**
  - *Hypothesis*: Do expiry anomalies repeat in temporal bursts or cluster across consecutive settlement dates?
  - *Finding*: Zero significant serial correlation or temporal clustering beyond random expectation.
- **[RQ8: Regulatory Reforms (2024–2026) Evaluation](file:///c:/Users/sawan/Downloads/Finance_project/expiry-watch/RQs/RQ8/RQ8_report_section_v2.pdf)**
  - *Hypothesis*: Did the SEBI Oct 2024 framework, Tuesday contract relocation (Sep 2025), and Closing Auction Session (CAS, Aug 2026) reduce or relocate anomalies?
  - *Finding*: No clear overall volume/volatility reduction. Suggestive relocation observed: the final bar carries a higher share of intraday variance post-reform.

---

## Interactive Dashboard (WP8)

Launch the Streamlit interactive dashboard from the repository root:

```bash
streamlit run src/step7_dashboard.py
```

The dashboard includes:
1. **MIRS Dashboard**: Surveillance rankings, filters, timeline, and score distributions.
2. **Forensic Deep-Dive**: Event-level breakdown and feature comparisons.
3. **ML Anomaly Decomposition**: Multi-model consensus (Isolation Forest, LOF, One-Class SVM).
4. **WP7 News Evidence Review**: Audited news items and timestamp verification.
5. **Methodology & Limitations**: Full mathematical definitions and surveillance constraints.

---

## Disclaimer

All indicators, models, and scores in this repository serve surveillance ranking and econometric research purposes only. They do not constitute evidence of legal wrongdoing or manipulation.
