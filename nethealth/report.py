import json
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any


HISTORY_PATH = Path.home() / ".nethealth" / "history.json"

# Keep the history file from growing unbounded over months of use. Shared by
# every writer (the `check --save json` CLI path and the TUI monitor loop).
MAX_HISTORY_ENTRIES = 5000

# Only the check keys the report knows how to aggregate are persisted, so a
# snapshot from the TUI (which also runs an SSL check) matches the shape the
# `check` CLI writes.
_RECORDED_CHECKS = ("dns", "ping", "http", "port")

# Number of recent samples shown in the sparkline column.
_SPARK_SAMPLES = 20
# Unicode block characters: ▁ = fail / poor, █ = ok / full
_SPARK_OK   = "█"
_SPARK_FAIL = "▁"


def _make_sparkline(booleans: list[bool]) -> str:
    """Convert a list of ok booleans → a Unicode block-char sparkline string."""
    return "".join(_SPARK_OK if b else _SPARK_FAIL for b in booleans)


def record_check(target: str, results: dict, path: Path | None = None) -> Path:
    """Append one check snapshot to history.json, trimming to MAX_HISTORY_ENTRIES.

    A corrupt/unreadable history file is not fatal -- it's replaced with a
    fresh list (the old bytes are left on disk untouched by not reading further).
    Returns the path written.
    """
    path = path or HISTORY_PATH
    path.parent.mkdir(exist_ok=True)

    history: list[dict] = []
    if path.exists():
        try:
            loaded = json.loads(path.read_text())
            if isinstance(loaded, list):
                history = loaded
        except Exception:
            history = []

    trimmed = {k: results[k] for k in _RECORDED_CHECKS if k in results}
    history.append({
        "timestamp": datetime.now().isoformat(),
        "target": target,
        "results": trimmed,
    })
    if len(history) > MAX_HISTORY_ENTRIES:
        history = history[-MAX_HISTORY_ENTRIES:]
    path.write_text(json.dumps(history, indent=2))
    return path


def _load_history(path: Path | None = None) -> list[dict]:
    # `path` defaults via `or` rather than `path: Path = HISTORY_PATH` in the
    # signature -- a default *parameter value* is bound once at function
    # definition time, so it would silently keep pointing at whatever
    # HISTORY_PATH was when this module was first imported even if the
    # module-level constant is reassigned later (as tests do).
    path = path or HISTORY_PATH
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

    Each per-check entry now includes a 'sparkline' string showing the
    pass/fail trend across the last _SPARK_SAMPLES results.
    """
    entries = _load_history()
    if not entries:
        return {
            "status": "empty",
            "message": (
                "No history yet. The report fills in automatically as checks run — "
                "leave the nethealth monitor open for a few minutes, or run "
                "'nethealth check google.com --save json' once to seed it."
            ),
        }

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

            # Sparkline: last _SPARK_SAMPLES results, oldest → newest left to right
            spark_window = values[-_SPARK_SAMPLES:]
            sparkline = _make_sparkline([v.get("status") == "ok" for v in spark_window])

            entry: dict[str, Any] = {
                "total": total,
                "passed": passed,
                "pass_pct": round(passed / total * 100, 1),
                "sparkline": sparkline,
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