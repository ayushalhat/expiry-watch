# WP7 News Evidence Audit — ExpiryWatch India

> **Surveillance priority only.** This audit records whether dated public-information evidence has been documented near selected expiries. It does not establish that information caused a price movement or determine intent.

## Implementation status

The previous WP7 code read a manually populated JSON file. It did not retrieve news or call an LLM, despite describing its contents as an LLM/RAG result. Its citations were host names rather than direct source links, did not carry article titles or publication times, and some entries exceeded the stated event window. The prior result also applied a second news discount to Step 4 MIRS, which was already discounted.

The corrected script, `src/step6_wp7_news.py`, is an evidence-catalogue validator and report generator. It is **not** an end-to-end retrieval or LLM application. Each item must contain a category, event date, factual summary, human-review status, public-availability timestamp and a direct source record with title, publisher, URL and timezone-aware publication timestamp. Publication after the expiry-close cutoff (15:30 IST) is rejected. Events outside plus/minus two calendar days are rejected.

## Current audit result

| Measure | Result |
|---|---:|
| Forensic dates | 17 |
| Dates with source-complete, human-reviewed evidence | 0 |
| Dates pending source review | 17 |
| Accepted evidence items | 0 |

The original source-less entries were preserved separately as `wp7_news_kb_legacy_unverified.json`; they are not used to score or display news. A pending result means the evidence record is incomplete. It does not mean that no relevant news existed.

## Score treatment

NES is retained only as an exploratory temporal-proximity index after an item passes validation and human review. It is not a calibrated measure of causal explanation. The WP7 score sensitivity starts from Step 4's pre-news composite U and replaces the Step 4 rule-based discount. It does not apply a second discount to the already-discounted base MIRS, and it does not change base tiers.

## Files

| File | Purpose |
|---|---|
| `wp7_news_kb.json` | Versioned evidence schema; currently all dates are pending |
| `wp7_news_kb_legacy_unverified.json` | Preserved pre-audit file; not consumed by the app |
| `wp7_nes_scores.csv` | Date-level validation status, base MIRS, exploratory NES and sensitivity |
| `wp7_evidence_packs.md` | Evidence cards with explicit pending status or validated source links |
| `wp7_summary.txt` | Run summary and current audit counts |

For the implementation critique and exact corrections, see [WP7_Implementation_Review.md](../../reports/WP7_Implementation_Review.md).
