from __future__ import annotations

import re
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack
from datetime import datetime, timezone
from pathlib import Path
from typing import IO


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _log_name(target: str) -> str:
    """Filesystem-safe, collision-free log name. The old `replace('.', '_')`
    mapped `a.b` and `a_b` to the same file and left IPv6 colons in place."""
    return "ping_" + re.sub(r"[^A-Za-z0-9-]", lambda m: f"_{ord(m.group()):x}_", target) + ".log"


def _ping_target(target: str, log_file: IO[str]) -> bool:
    """Ping ``target`` once and append one timestamped line to its log."""
    timestamp = _utc_now()
    try:
        proc = subprocess.run(
            ["ping", "-c", "1", "-W", "1", target],
            capture_output=True,
            text=True,
            timeout=3,  # -W bounds the reply wait, not DNS resolution
        )
    except Exception as e:
        log_file.write(f"{timestamp} ERROR {e}\n")
        return False

    if proc.returncode != 0:
        log_file.write(f"{timestamp} TIMEOUT\n")
        return False

    # Typically "64 bytes from ...: icmp_seq=1 ttl=64 time=0.045 ms"
    latency_line = next((l for l in proc.stdout.splitlines() if "time=" in l), None)
    suffix = f" {latency_line.split('time=')[-1]}" if latency_line else ""
    log_file.write(f"{timestamp} OK{suffix}\n")
    return True


def monitor_ping(
    targets: list[str],
    interval: int = 1,
    duration: int = 300,
    log_dir: str = "nethealth-logs",
) -> bool:
    """
    Long-running, concurrent, timestamped ping monitor. Returns False if
    the run was cut short by Ctrl-C.
    """
    Path(log_dir).mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    end_time = started + duration
    stats = {t: {"sent": 0, "received": 0} for t in targets}
    completed = True

    with ExitStack() as stack:
        logs = {
            t: stack.enter_context(open(Path(log_dir) / _log_name(t), "a", buffering=1, encoding="utf-8"))
            for t in targets
        }
        for log in logs.values():
            log.write(f"# Started ping monitor at {_utc_now()} UTC\n")

        print(f"📡 Monitoring {len(targets)} targets. Press Ctrl-C to stop.")
        try:
            with ThreadPoolExecutor(max_workers=len(targets)) as executor:
                while time.monotonic() < end_time:
                    cycle_start = time.monotonic()
                    for t, ok in zip(targets, executor.map(lambda t: _ping_target(t, logs[t]), targets)):
                        stats[t]["sent"] += 1
                        stats[t]["received"] += ok
                    # Interval is measured from the cycle start, so slow pings
                    # don't stretch the sampling period.
                    time.sleep(max(0.0, interval - (time.monotonic() - cycle_start)))
        except KeyboardInterrupt:
            print("\n🛑 Interrupt received. Cleaning up...")
            completed = False
        finally:
            print("\n--- Monitoring Summary ---")
            print(f"Duration: {time.monotonic() - started:.1f}s")
            footer = "Interrupted" if not completed else "Finished"
            for target, s in stats.items():
                loss = (1 - s["received"] / s["sent"]) * 100 if s["sent"] else 0.0
                print(f"Target {target:15}: Sent={s['sent']}, Received={s['received']}, Loss={loss:.1f}%")
                logs[target].write(f"# {footer} at {_utc_now()} UTC\n")
                logs[target].write(f"# Summary: Sent={s['sent']}, Received={s['received']}, Loss={loss:.1f}%\n")

    return completed
