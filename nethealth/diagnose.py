"""
nethealth/diagnose.py — turn raw check results into a plain-language verdict.

Every other part of nethealth reports numbers and status flags for people who
already know what DNS and latency mean. This module answers the only question a
non-technical user is actually asking — "is my internet working, and if not,
what's wrong?" — in a full sentence, with the technical detail kept one layer
down (the `details` list) and a concrete next step (`suggestions`).

Pure logic, no I/O: `diagnose()` takes the dicts the check functions already
return and produces a `Diagnosis`. The CLI (`nethealth status`) runs the checks
and renders the result.
"""
from __future__ import annotations

from dataclasses import dataclass, field

# Plain-language "slow" thresholds. Deliberately generous — this is the
# "should a normal person care?" line, not the engineer's one.
PING_SLOW_MS = 150.0
PING_VERY_SLOW_MS = 400.0
DNS_SLOW_MS = 300.0
HTTP_SLOW_MS = 2000.0

OK = "ok"
WARN = "warn"
DOWN = "down"


@dataclass
class Diagnosis:
    severity: str  # "ok" | "warn" | "down"
    headline: str  # one plain-language sentence, no jargon
    details: list[str] = field(default_factory=list)  # supporting facts, mild jargon fine
    suggestions: list[str] = field(default_factory=list)  # concrete next steps


def _avg(result: dict | None) -> float | None:
    if not result:
        return None
    for key in ("avg_ms", "latency"):
        if result.get(key) is not None:
            return float(result[key])
    return None


def _ok(result: dict | None) -> bool:
    return bool(result) and result.get("status") == "ok"


def _failed(result: dict | None) -> bool:
    return bool(result) and result.get("status") not in ("ok", None)


def diagnose(
    *,
    gateway: dict | None = None,
    dns: dict | None = None,
    ping: dict | None = None,
    http: dict | None = None,
    target: str = "that site",
) -> Diagnosis:
    """Build a plain-language Diagnosis from any subset of check results.

    Checks are considered in order of "how close to home the problem is":
    router first, then reaching the internet at all, then name lookups, then
    the specific site. The first broken link in that chain is the headline.
    """
    # 1. Can't even reach the router/modem.
    if _failed(gateway):
        return Diagnosis(
            DOWN,
            "No network connection — your device can't reach your router or modem.",
            details=[gateway.get("error", "The default gateway did not respond.")],
            suggestions=[
                "Check your Wi-Fi is connected, or that the network cable is plugged in.",
                "Restart your router/modem: unplug it, wait 30 seconds, plug it back in.",
            ],
        )

    reached_internet = _ok(ping) or _ok(http)
    tried_internet = ping is not None or http is not None

    # 2. On the local network, but nothing beyond it answers.
    if tried_internet and not reached_internet and (dns is None or _failed(dns)):
        return Diagnosis(
            DOWN,
            "No internet connection — your device is on the local network but can't reach anything online.",
            details=_facts(gateway=gateway, dns=dns, ping=ping, http=http),
            suggestions=[
                "Restart your router/modem (unplug 30 seconds, plug back in).",
                "If other devices are also offline, contact your internet provider.",
            ],
        )

    # 3. Internet is reachable by IP, but name lookups fail — classic DNS problem.
    if _failed(dns) and (_ok(ping) or _ok(http)):
        return Diagnosis(
            DOWN,
            "You're connected, but web addresses aren't being looked up — this is usually a DNS problem.",
            details=[dns.get("error", "DNS resolution failed.")]
            + _facts(gateway=gateway, ping=ping, http=http),
            suggestions=[
                "Try setting your DNS servers to 1.1.1.1 and 8.8.8.8.",
                "Restarting the router often clears this too.",
            ],
        )

    # 4. Everything general works, but the specific site doesn't.
    if _failed(http) and (_ok(ping) or _ok(dns)):
        return Diagnosis(
            WARN,
            f"Your internet is working, but {target} isn't responding right now.",
            details=[http.get("error", "The web request failed.")]
            + _facts(gateway=gateway, dns=dns, ping=ping),
            suggestions=[
                f"The problem is probably with {target}, not your connection — try again later.",
                "Other websites should still work normally.",
            ],
        )

    # 5. Nothing is broken — is anything slow?
    slow_notes: list[str] = []
    ping_avg = _avg(ping)
    dns_avg = _avg(dns)
    http_avg = _avg(http)

    very_slow = ping_avg is not None and ping_avg >= PING_VERY_SLOW_MS
    if ping_avg is not None and ping_avg >= PING_SLOW_MS:
        slow_notes.append(f"response times are high ({ping_avg:.0f} ms to {target})")
    if dns_avg is not None and dns_avg >= DNS_SLOW_MS:
        slow_notes.append(f"web-address lookups are slow ({dns_avg:.0f} ms)")
    if http_avg is not None and http_avg >= HTTP_SLOW_MS:
        slow_notes.append(f"pages are loading slowly ({http_avg / 1000:.1f} s)")

    facts = _facts(gateway=gateway, dns=dns, ping=ping, http=http)

    if slow_notes:
        lead = "Your internet is working, but it's very slow right now" if very_slow \
            else "Your internet is working, but a little slower than usual"
        return Diagnosis(
            WARN,
            f"{lead} — {slow_notes[0]}.",
            details=slow_notes[1:] + facts,
            suggestions=[
                "If it stays slow, restart your router and check nothing large is downloading.",
                "Run `nethealth speed` to measure your download speed.",
            ],
        )

    if not tried_internet and dns is None:
        # Only a gateway check was supplied and it passed.
        return Diagnosis(
            OK,
            "Your device is connected to the local network.",
            details=facts,
        )

    return Diagnosis(
        OK,
        "Your internet is working normally.",
        details=facts,
    )


def _facts(*, gateway=None, dns=None, ping=None, http=None) -> list[str]:
    """Supporting one-liners for the details section — mild jargon is fine here,
    it's the layer under the headline."""
    out: list[str] = []
    if _ok(gateway) and gateway.get("avg_ms") is not None:
        out.append(f"Router responds in {gateway['avg_ms']:.0f} ms.")
    if _ok(dns) and _avg(dns) is not None:
        out.append(f"Web-address lookup: {_avg(dns):.0f} ms.")
    if _ok(ping) and _avg(ping) is not None:
        out.append(f"Connection response time: {_avg(ping):.0f} ms average.")
    if _ok(http):
        code = http.get("code", "?")
        lat = http.get("latency")
        lat_s = f" in {lat:.0f} ms" if lat is not None else ""
        out.append(f"Website replied (HTTP {code}){lat_s}.")
    return out
