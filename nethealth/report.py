from __future__ import annotations

import csv
import json
import os
import threading
from collections import Counter, defaultdict
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


# The TUI records from one worker thread per target, so concurrent writers are
# the normal case. Read-modify-write without this lock lost entries.
_HISTORY_LOCK = threading.Lock()


def record_check(target: str, results: dict, path: Path | None = None) -> Path:
    """Append one check snapshot to history.json, trimming to MAX_HISTORY_ENTRIES.

    The write is atomic (temp file + replace), so a crash mid-write can't
    truncate the history. A corrupt/unreadable file is moved aside to
    ``history.json.corrupt-<timestamp>`` rather than overwritten -- the old
    code's docstring promised it was left alone, but it was clobbered.
    Returns the path written.
    """
    path = path or HISTORY_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    trimmed = {k: results[k] for k in _RECORDED_CHECKS if k in results}
    entry = {"timestamp": datetime.now().isoformat(), "target": target, "results": trimmed}

    with _HISTORY_LOCK:
        history: list[dict] = []
        if path.exists():
            try:
                loaded = json.loads(path.read_text(encoding="utf-8"))
                if not isinstance(loaded, list):
                    raise ValueError("history root is not a list")
                history = loaded
            except Exception:
                stamp = datetime.now().strftime("%Y%m%dT%H%M%S")
                path.replace(path.with_name(f"{path.name}.corrupt-{stamp}"))

        history.append(entry)
        history = history[-MAX_HISTORY_ENTRIES:]
        tmp = path.with_name(f"{path.name}.tmp")
        tmp.write_text(json.dumps(history, indent=2), encoding="utf-8")
        os.replace(tmp, path)
    return path


def record_check_csv(target: str, results: dict, path: Path) -> Path:
    """Append one row per check to a CSV history file (`check --save csv`)."""
    from nethealth.formatting import LABELS, detail

    path.parent.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().isoformat()
    rows = [
        {"timestamp": ts, "target": target, "check": LABELS[name],
         "status": results[name]["status"], "detail": detail(name, results[name])}
        for name in _RECORDED_CHECKS if name in results
    ]
    with _HISTORY_LOCK:
        write_header = not path.exists()
        with open(path, "a", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=["timestamp", "target", "check", "status", "detail"])
            if write_header:
                writer.writeheader()
            writer.writerows(rows)
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
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []
    return loaded if isinstance(loaded, list) else []


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