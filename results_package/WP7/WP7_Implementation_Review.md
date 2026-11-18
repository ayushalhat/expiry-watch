# WP7 implementation review

## Critical findings in the original implementation

1. **It was not an end-to-end LLM/RAG application.** `step6_wp7_news.py` only read a pre-filled JSON file. It had no retrieval, LLM request, prompt log, source-resolution step, or model-version capture. The dashboard and summary nevertheless described news as sourced by an agent.
2. **The source records were not auditable.** The knowledge base stored host names such as `rbi.org.in` rather than article URLs, titles, publication times, or captured evidence. A professor or reviewer could not open the cited document and verify the claim.
3. **The time window contradicted the method.** The UI said plus/minus two trading days, while records applied the flag to older items, including RBI decisions eight days before an expiry and a US rate decision eight days before another.
4. **The text overclaimed what a news match means.** Notes said that news “fully explains” events, treated missing search results as proof that no news existed, and described the negative controls as passing. Temporal overlap does not prove causality or validate the size of a discount.
5. **MIRS was discounted twice.** Step 4's MIRS already equals its pre-news composite U times the fixed Step 4 discount. The WP7 script multiplied that already-discounted MIRS by a second discount.
6. **The dashboard described the wrong score.** It showed `MIRS = 0.5T + 0.3U + 0.2EVR` and called U an ML consensus. The implemented Step 4 score is a weighted mean of A, T, R, and Rec; Step 3 ML consensus is not in base MIRS.
7. **Several specific facts needed source checks.** Examples include a NIFTY expiry weekday change, the claim that a one-day NIFTY return was 1.89% on 12 Sep 2024 (the close-to-close return was 1.89%, but the intraday bar data should not be conflated with the close), and a June 2026 note that called a component T value “MIRS=1.00.” Source-less assertions were not safe to retain as evidence.
8. **The dashboard had brittle dependencies.** It required every optional SHAP output to exist, cached files without tracking their modification times, fetched its logo from the network at app load, and could fail opaquely on a legacy WP7 CSV.

## Corrections made

- Replaced the domain-only knowledge base with a versioned, fail-closed schema. The previous file is preserved as `outputs/wp7_news_kb_legacy_unverified.json` and is not consumed by the app.
- Reworked `src/step6_wp7_news.py` to reject unreviewed evidence, host-only citations, URLs without direct HTTPS links, missing titles/publishers, timestamps without time zones, and material published after the 15:30 IST expiry-close cutoff. The allowed event window is stated as plus/minus two **calendar** days.
- Missing or rejected evidence now yields `SOURCE_AUDIT_PENDING` and blank NES values. It does not yield NES=0 or a claim that no news existed.
- WP7 sensitivity is calculated from U, replacing the Step 4 discount; it never discounts base MIRS a second time and never changes base tiers. The score is explicitly exploratory and non-causal.
- Replaced categorical verdicts with a neutral surveillance note and source-validation details. The current record reports 0 of 17 dates with source-complete, human-reviewed items; it does not treat this as evidence of no relevant news.
- Corrected the dashboard's MIRS formula, tier description, WP7 labels, source links, optional-file handling, data-cache invalidation, and missing-data messages. Removed the network-loaded logo.

## Remaining boundary

The current code validates a curated source catalogue; it does **not** retrieve articles or call an LLM. Therefore the original WP7 claim of a completed LLM/RAG news-attribution system was not supportable. The safer implementation keeps the evidence workflow usable without claiming that retrieval or model inference occurred. To make this genuinely end-to-end LLM/RAG, a retrieval provider and model API still need to be configured, with source snapshots, prompt/model logs, and mandatory human approval before an item is marked verified.

All scores remain surveillance-priority aids. The available two-hour spot data cannot establish that a news item caused any observed movement.
