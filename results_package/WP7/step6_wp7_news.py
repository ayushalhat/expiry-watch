"""WP7 evidence catalogue and audit.

This script does not retrieve news or call an LLM. It validates a human-reviewed
knowledge base, enforces the expiry-close information cutoff, and builds cards
and an exploratory score only from complete, timestamped evidence.

Run from the project root: python src/step6_wp7_news.py
"""
from __future__ import annotations

import json
import math
from datetime import date, datetime, time, timedelta
from pathlib import Path
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "outputs"
KB_PATH = OUT / "wp7_news_kb.json"
FORENSICS_PATH = OUT / "forensics" / "forensics_summary.csv"
MIRS_WF_PATH = OUT / "step4_mirs_walkforward.csv"
MIRS_RETRO_PATH = OUT / "step4_mirs_RETROSPECTIVE.csv"
IST = ZoneInfo("Asia/Kolkata")
MARKET_CLOSE = time(15, 30)
SUPPORTED_CATEGORIES = {"macro", "regulatory", "corporate_index", "global_market"}


def load_json(path: Path) -> dict:
    try:
        with path.open(encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError as exc:
        raise SystemExit(f"Required file not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise SystemExit(f"Invalid JSON in {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise SystemExit(f"Expected a JSON object in {path}")
    return data


def load_mirs(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise SystemExit(f"Required MIRS file not found: {path}")
    frame = pd.read_csv(path, parse_dates=[0], index_col=0)
    frame.index = pd.to_datetime(frame.index).normalize()
    if frame.index.has_duplicates:
        raise SystemExit(f"Duplicate dates in {path}")
    return frame


def iso_datetime(value: object) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed.astimezone(IST)


def cutoff_for(event_date: date) -> datetime:
    return datetime.combine(event_date, MARKET_CLOSE, tzinfo=IST)


def valid_url(value: object) -> bool:
    if not isinstance(value, str):
        return False
    parsed = urlparse(value.strip())
    return parsed.scheme == "https" and bool(parsed.netloc) and not parsed.netloc.endswith("example.com")


def validate_item(item: object, event_date: date) -> tuple[bool, list[str], dict]:
    errors: list[str] = []
    if not isinstance(item, dict):
        return False, ["Evidence item must be an object"], {}
    category = item.get("category")
    if category not in SUPPORTED_CATEGORIES:
        errors.append("category must be one of " + ", ".join(sorted(SUPPORTED_CATEGORIES)))
    item_date = item.get("event_date")
    try:
        parsed_date = date.fromisoformat(item_date) if isinstance(item_date, str) else None
    except ValueError:
        parsed_date = None
    if parsed_date is None:
        errors.append("event_date must use YYYY-MM-DD")
    elif abs((parsed_date - event_date).days) > 2:
        errors.append("event_date is outside the allowed +/-2 calendar-day window")
    summary = item.get("summary")
    if not isinstance(summary, str) or len(summary.strip()) < 12:
        errors.append("summary must contain a concise factual description")
    status = item.get("review_status")
    if status != "verified":
        errors.append("review_status is not verified by a human reviewer")
    sources = item.get("sources")
    if not isinstance(sources, list) or not sources:
        errors.append("at least one source is required")
        sources = []
    normalized_sources = []
    for n, src in enumerate(sources, 1):
        if not isinstance(src, dict):
            errors.append(f"source {n} must be an object")
            continue
        title = src.get("title")
        publisher = src.get("publisher")
        url = src.get("url")
        published = iso_datetime(src.get("published_at"))
        if not isinstance(title, str) or not title.strip():
            errors.append(f"source {n} needs a title")
        if not isinstance(publisher, str) or not publisher.strip():
            errors.append(f"source {n} needs a publisher")
        if not valid_url(url):
            errors.append(f"source {n} needs a direct HTTPS article/source URL")
        if published is None:
            errors.append(f"source {n} needs an ISO timestamp with timezone")
        elif published > cutoff_for(event_date):
            errors.append(f"source {n} was published after the 15:30 IST information cutoff")
        normalized_sources.append({
            "title": title.strip() if isinstance(title, str) else "",
            "publisher": publisher.strip() if isinstance(publisher, str) else "",
            "url": url.strip() if isinstance(url, str) else "",
            "published_at": published,
        })
    available_at = iso_datetime(item.get("available_at"))
    if available_at is None:
        errors.append("available_at needs an ISO timestamp with timezone")
    elif available_at > cutoff_for(event_date):
        errors.append("item was not public by the 15:30 IST information cutoff")
    elif parsed_date is not None and available_at.date() < parsed_date:
        errors.append("available_at precedes the event date")
    if available_at is not None:
        for n, source in enumerate(normalized_sources, 1):
            if source["published_at"] is not None and source["published_at"] > available_at:
                errors.append(f"source {n} was published after the item availability timestamp")
    return not errors, errors, {**item, "category": category, "sources_normalized": normalized_sources}


def score_entry(entry: object, event_date: date) -> tuple[float, list[dict], list[str]]:
    """Exploratory co-occurrence index; not a causal or calibrated explanation score."""
    if not isinstance(entry, dict):
        return math.nan, [], ["No reviewed entry"]
    if entry.get("review_status") != "reviewed":
        return math.nan, [], ["Date entry has not passed human review"]
    raw_items = entry.get("items", [])
    if not isinstance(raw_items, list):
        return math.nan, [], ["items must be a list"]
    accepted = []
    errors = []
    for i, item in enumerate(raw_items, 1):
        valid, item_errors, normalized = validate_item(item, event_date)
        if valid:
            accepted.append(normalized)
        else:
            errors.extend(f"Item {i}: {message}" for message in item_errors)
    if not accepted:
        return math.nan, [], errors or ["No reviewed evidence items"]

    # Scores are conservative tags for information proximity, not evidence that
    # the information caused the move. Exact-day public information dominates.
    weights = {"macro": 0.6, "regulatory": 0.6, "corporate_index": 0.6, "global_market": 0.4}
    values = []
    for item in accepted:
        d = date.fromisoformat(item["event_date"])
        if d == event_date:
            values.append(1.0)
        else:
            values.append(weights[item["category"]])
    return max(values), accepted, errors


def fmt(value: object, digits: int = 3) -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "Pending"
    return f"{number:.{digits}f}" if np.isfinite(number) else "Pending"


def source_markdown(source: dict) -> str:
    published = source["published_at"].strftime("%Y-%m-%d %H:%M %Z")
    return f"[{source['publisher']}: {source['title']}]({source['url']}) (published {published})"


def main() -> None:
    if not FORENSICS_PATH.exists():
        raise SystemExit(f"Required forensic-date file not found: {FORENSICS_PATH}")
    forensics = pd.read_csv(FORENSICS_PATH, parse_dates=["date"])
    if "date" not in forensics or forensics["date"].duplicated().any():
        raise SystemExit("Forensics file must have one unique row per date")
    forensics["date"] = forensics["date"].dt.normalize()
    kb_root = load_json(KB_PATH)
    if kb_root.get("schema_version") != 2 or not isinstance(kb_root.get("dates"), dict):
        raise SystemExit(
            "Knowledge base is not schema v2. Use entries with reviewed evidence items; "
            "domain-only legacy citations are deliberately rejected."
        )
    kb = kb_root["dates"]
    mirs_wf, mirs_retro = load_mirs(MIRS_WF_PATH), load_mirs(MIRS_RETRO_PATH)

    rows, cards = [], []
    for _, frow in forensics.iterrows():
        dt = frow["date"].date()
        key = dt.isoformat()
        entry = kb.get(key, {})
        nes, valid_items, errors = score_entry(entry, dt)
        source_frame = mirs_wf if pd.Timestamp(dt) in mirs_wf.index else mirs_retro
        score_row = source_frame.loc[pd.Timestamp(dt)] if pd.Timestamp(dt) in source_frame.index else None
        base_mirs = float(score_row["MIRS"]) if score_row is not None and pd.notna(score_row.get("MIRS")) else math.nan
        pre_news = float(score_row["U"]) if score_row is not None and pd.notna(score_row.get("U")) else math.nan
        tier = str(score_row["tier"]) if score_row is not None else "Unknown"
        # Replace Step 4's existing mechanical event/gap discount using U;
        # never apply a second discount to the already-discounted MIRS value.
        sensitivity = pre_news * (1 - 0.5 * nes) if np.isfinite(nes) and np.isfinite(pre_news) else math.nan
        status = "REVIEWED" if valid_items else "SOURCE_AUDIT_PENDING"
        reasons = sorted(set(errors))
        note = (
            "Public information was documented near the expiry cutoff. This is temporal context only; "
            "the available spot data cannot establish that it explains the observed move."
            if valid_items else
            "No source-complete, human-reviewed evidence item passed validation. This means evidence is pending, not that no relevant news existed."
        )
        refs = [src for item in valid_items for src in item["sources_normalized"]]
        rows.append({
            "date": key,
            "expiry_type": frow.get("expiry_type", ""),
            "tier_base": tier,
            "MIRS_base": base_mirs,
            "U_pre_news": pre_news,
            "NES_exploratory": nes,
            "MIRS_WP7_sensitivity": sensitivity,
            "verified_item_count": len(valid_items),
            "status": status,
            "audit_notes": "; ".join(reasons),
            "analyst_note": note,
            "sources": "; ".join(src["url"] for src in refs),
            "retrieval_date": kb_root.get("retrieval_date", ""),
            "cutoff_ist": cutoff_for(dt).isoformat(),
            "selected_because": frow.get("selected_because", ""),
        })
        source_lines = []
        for item in valid_items:
            source_bullets = "\n".join(
                f"  - {source_markdown(source)}" for source in item["sources_normalized"]
            )
            source_lines.append(
                f"- **{item['category']}**, event date {item['event_date']}: {item['summary']}\n"
                f"  - Public by: {iso_datetime(item['available_at']).strftime('%Y-%m-%d %H:%M %Z')}\n"
                f"  - Sources:\n{source_bullets}"
            )
        if not source_lines:
            source_lines = ["- Evidence pending. Legacy domain-only entries were rejected because they do not identify a retrievable source or timestamp."]
        cards.append(f"""## {key} — {frow.get('expiry_type', 'Unknown')} expiry

**Selected because:** {frow.get('selected_because', '')}  
**Information cutoff:** {cutoff_for(dt).strftime('%Y-%m-%d %H:%M %Z')}  
**Base tier / MIRS:** {tier} / {fmt(base_mirs)}  
**Evidence review status:** {status}

### Public information recorded
{chr(10).join(source_lines)}

### Scoring
- **NES (exploratory):** {fmt(nes, 2)}
- **MIRS before news adjustment (U):** {fmt(pre_news)}
- **WP7 sensitivity:** {fmt(sensitivity)}
- WP7 sensitivity replaces Step 4's existing rule-based discount; it is not applied to the already-discounted base MIRS. It is exploratory and does not change the reported tier.

### Surveillance note
{note}

> **Surveillance priority only.** Co-occurrence is not causation; no conclusion about intent, innocence, or legal responsibility follows from these data.

---""")

    scores = pd.DataFrame(rows)
    scores.to_csv(OUT / "wp7_nes_scores.csv", index=False, na_rep="")
    valid_count = int((scores["status"] == "REVIEWED").sum())
    total_items = int(scores["verified_item_count"].sum())
    summary = f"""# WP7 News Evidence Audit — ExpiryWatch India

## Scope and method

This application validates a curated evidence catalogue; it does not itself search the web or call an LLM. Each evidence item must have a category, event date, factual summary, human review status, public-availability timestamp and at least one direct HTTPS source with title, publisher and timezone-aware publication timestamp. Sources published after the 15:30 IST expiry-close cutoff are rejected. Items outside the stated +/-2 calendar-day window are rejected. These checks address provenance and timing; they do not prove that an item caused a price move.

NES is an exploratory temporal-proximity index. It is not a calibrated causal explanation score. The sensitivity output starts from Step 4's pre-news component U, replaces Step 4's mechanical discount, leaves the base MIRS and tier unchanged, and is explicitly not inferential.

## Audit result

- Forensic dates: {len(scores)}
- Dates with at least one source-complete, human-reviewed item: {valid_count}
- Source-complete reviewed items: {total_items}
- Dates pending review: {len(scores) - valid_count}
- Legacy domain-only citations were not accepted as evidence.

See `wp7_nes_scores.csv` and `wp7_evidence_packs.md` for date-level audit results.
"""
    (OUT / "wp7_evidence_packs.md").write_text(
        "> **Surveillance priority only.** This evidence catalogue reports public information near expiry dates; it does not establish causation or wrongdoing.\n\n"
        + "\n\n".join(cards), encoding="utf-8"
    )
    (OUT / "wp7_summary.txt").write_text(summary, encoding="utf-8")
    print(summary)


if __name__ == "__main__":
    main()
