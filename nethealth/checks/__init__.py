"""
nethealth/checks — every individual check, plus the one place that knows how
to run a set of them against a target.

Every check returns a plain dict with at least ``name`` and ``status``
("ok" | "fail"); a failure carries ``error``. The CLI, the TUI and the history
writer all go through ``run_target_checks`` so the list of per-target checks
lives here once instead of being hand-copied into each front end.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from typing import Callable, Iterable

from nethealth.checks.dns import dns_check
from nethealth.checks.http import http_check
from nethealth.checks.ping import ping_check
from nethealth.checks.port import port_check
from nethealth.checks.ssl import ssl_check
from nethealth.checks.traceroute import traceroute_check

CheckFn = Callable[[str], dict]

# Looked up by name at call time (not bound into a closure at import), so a
# test can monkeypatch an entry and every front end sees the fake.
TARGET_CHECKS: dict[str, CheckFn] = {
    "dns": dns_check,
    "ping": ping_check,
    "http": http_check,
    "port": port_check,
    "ssl": lambda target: ssl_check(target, timeout=5),
    "traceroute": lambda target: traceroute_check(target, max_hops=15),
}

# What `nethealth check` runs by default (traceroute is opt-out there).
CLI_CHECKS = ("dns", "ping", "http", "port", "traceroute")
# What the TUI monitor loop runs every cycle.
MONITOR_CHECKS = ("dns", "ping", "http", "port", "ssl")


def safe_run(name: str, fn: CheckFn, target: str) -> dict:
    """Run one check, turning an unexpected exception into the normal failure
    shape so one broken check can't blank a whole cycle for a target."""
    try:
        return fn(target)
    except Exception as exc:  # noqa: BLE001 - isolation is the point
        return {"name": name.upper(), "status": "fail", "error": f"internal error: {exc}"}


def run_target_checks(target: str, names: Iterable[str]) -> dict[str, dict]:
    """Run the named checks against ``target`` concurrently.

    Returns ``{name: result}`` in the order ``names`` was given. Wall time is
    roughly the slowest single check rather than the sum of them.
    """
    names = list(names)
    with ThreadPoolExecutor(max_workers=max(1, len(names))) as pool:
        futures = {n: pool.submit(safe_run, n, TARGET_CHECKS[n], target) for n in names}
        return {n: futures[n].result() for n in names}
