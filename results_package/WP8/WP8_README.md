# WP8 — Interactive Dashboard

## ExpiryWatch India (NIFTY, spot-only, Tier-A framework)

Run from the project root:

```text
streamlit run src/step7_dashboard.py
```

The dashboard requires the precomputed files under `outputs/`. It checks for missing or legacy-schema inputs at startup and reports which files need regeneration. Optional SHAP outputs are shown only when present. Cached data is invalidated when its source files change.

## Pages

1. **MIRS Dashboard:** walk-forward/retrospective selector, expiry type and tier filters, ranked table, distributions and timeline.
2. **Forensic Deep-Dive:** selected event card, source-review status, feature snapshot and MIRS components.
3. **ML / Step 2 Residual:** residual model, SHAP summary if available, unsupervised score distributions and component decomposition.
4. **WP7 News Evidence Review:** curated evidence links, timestamps, human-review status, audit notes and exploratory sensitivity.
5. **Methodology:** formulas, tier construction, known limitations and post-hoc settings.

## MIRS-lite formula

`U = 0.25A + 0.45T + 0.10R + 0.20Rec` and `MIRS = U × (1 − 0.5 × news_expl)`.

Step 3 ML consensus is not in base MIRS. Tiers use component-signal rules; they are not thresholds on the numeric MIRS value. Red is not assignable with spot-only data.

## WP7 boundary

`src/step6_wp7_news.py` validates a manually curated evidence catalogue. It does not retrieve news or call an LLM. Evidence without direct links, publication timestamps, availability-before-close checks and human review remains pending. WP7 sensitivity replaces the Step 4 discount using U; it does not discount base MIRS twice and does not change tiers. A pending record does not mean there was no relevant information.

All displayed scores rank surveillance priority only and do not establish causation or intent.
