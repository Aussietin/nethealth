import json
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any


HISTORY_PATH = Path.home() / ".nethealth" / "history.json"


def _load_history(path: Path = HISTORY_PATH) -> list[dict]:
    if not path.exists():
        return []
    try:
        return json.loads(path.read_text())
    except Exception:
        return []


def generate_report(target: str | None = None, last: int | None = None) -> dict:
    """
    Aggregate ~/.nethealth/history.json into per-target stats.
    Returns dict with keys: targets, date_range, entries_total, per_target.
    """
    entries = _load_history()
    if not entries:
        return {"status": "empty", "message": "No history found. Run nethealth check --save json first."}

    if target:
        entries = [e for e in entries if e.get("target") == target]

    if last:
        entries = entries[-last:]

    if not entries:
        return {"status": "empty", "message": f"No history for target '{target}'."}

    timestamps = [e["timestamp"] for e in entries if "timestamp" in e]
    date_range = (timestamps[0][:19], timestamps[-1][:19]) if timestamps else (None, None)

    # Group by target
    by_target: dict[str, list[dict]] = defaultdict(list)
    for e in entries:
        by_target[e.get("target", "unknown")].append(e.get("results", {}))

    per_target = {}
    for tgt, runs in by_target.items():
        stats: dict[str, Any] = {}
        for check in ("dns", "ping", "http", "port"):
            values = [r[check] for r in runs if check in r]
            if not values:
                continue
            passed = sum(1 for v in values if v.get("status") == "ok")
            total = len(values)
            entry: dict[str, Any] = {
                "total": total,
                "passed": passed,
                "pass_pct": round(passed / total * 100, 1),
            }
            if check == "dns":
                lats = [v["latency"] for v in values if v.get("status") == "ok" and "latency" in v]
                if lats:
                    entry["avg_latency_ms"] = round(sum(lats) / len(lats), 1)
                    entry["min_latency_ms"] = round(min(lats), 1)
                    entry["max_latency_ms"] = round(max(lats), 1)
            if check == "ping":
                avgs = [v["avg_ms"] for v in values if v.get("status") == "ok" and v.get("avg_ms") is not None]
                if avgs:
                    entry["avg_ms"] = round(sum(avgs) / len(avgs), 1)
                    entry["min_ms"] = round(min(avgs), 1)
                    entry["max_ms"] = round(max(avgs), 1)
            if check == "http":
                codes = [v.get("code") for v in values if v.get("status") == "ok" and v.get("code")]
                lats = [v["latency"] for v in values if v.get("status") == "ok" and "latency" in v]
                if codes:
                    from collections import Counter
                    entry["common_codes"] = dict(Counter(codes).most_common(3))
                if lats:
                    entry["avg_latency_ms"] = round(sum(lats) / len(lats), 1)
            stats[check] = entry
        per_target[tgt] = stats

    return {
        "status": "ok",
        "entries_total": len(entries),
        "date_range": date_range,
        "per_target": per_target,
    }