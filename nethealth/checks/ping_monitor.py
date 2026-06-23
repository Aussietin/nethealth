import subprocess
import time
import threading
from datetime import datetime
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor


def _ping_target(target, log_file):
    """Internal helper to ping a single target and log it."""
    timestamp = datetime.utcnow().isoformat(timespec="seconds")
    try:
        proc = subprocess.run(
            ["ping", "-c", "1", "-W", "1", target],
            capture_output=True,
            text=True,
        )

        if proc.returncode == 0:
            # extract latency if present
            latency_line = next(
                (l for l in proc.stdout.splitlines() if "time=" in l), None
            )
            if latency_line:
                # Typically format is "64 bytes from ...: icmp_seq=1 ttl=64 time=0.045 ms"
                log_file.write(f"{timestamp} OK {latency_line.split('time=')[-1]}\n")
            else:
                log_file.write(f"{timestamp} OK\n")
            return True
        else:
            log_file.write(f"{timestamp} TIMEOUT\n")
            return False
    except Exception as e:
        log_file.write(f"{timestamp} ERROR {e}\n")
        return False


def monitor_ping(
    targets,
    interval=1,
    duration=300,
    log_dir="nethealth-logs",
):
    """
    Long-running, concurrent, timestamped ping monitor.
    """
    Path(log_dir).mkdir(parents=True, exist_ok=True)
    end_time = time.time() + duration
    
    start_ts = datetime.utcnow()
    logs = {}
    stats = {t: {"sent": 0, "received": 0} for t in targets}
    
    for t in targets:
        safe = t.replace(".", "_")
        logs[t] = open(Path(log_dir) / f"ping_{safe}.log", "a", buffering=1)
        logs[t].write(f"# Started ping monitor at {start_ts.isoformat()} UTC\n")

    stop_event = threading.Event()
    completed = True

    print(f"📡 Monitoring {len(targets)} targets. Press Ctrl-C to stop.")

    try:
        with ThreadPoolExecutor(max_workers=len(targets)) as executor:
            while time.time() < end_time and not stop_event.is_set():
                futures = []
                for target in targets:
                    stats[target]["sent"] += 1
                    futures.append(executor.submit(_ping_target, target, logs[target]))
                
                # Wait for all pings in this interval to finish
                for i, future in enumerate(futures):
                    if future.result():
                        stats[targets[i]]["received"] += 1
                
                # Sleep briefly if we have time left in the interval
                # This is more responsive to Ctrl-C than a single long sleep
                sleep_until = time.time() + interval
                while time.time() < sleep_until and not stop_event.is_set():
                    time.sleep(0.1)

    except KeyboardInterrupt:
        print("\n🛑 Interrupt received. Cleaning up...")
        stop_event.set()
        completed = False
    finally:
        end_ts = datetime.utcnow()
        duration_actual = (end_ts - start_ts).total_seconds()
        
        print("\n--- Monitoring Summary ---")
        print(f"Duration: {duration_actual:.1f}s")
        for target, s in stats.items():
            loss = 0
            if s["sent"] > 0:
                loss = (1 - s["received"] / s["sent"]) * 100
            print(f"Target {target:15}: Sent={s['sent']}, Received={s['received']}, Loss={loss:.1f}%")
            
            logs[target].write(f"# Interrupted at {end_ts.isoformat()} UTC\n")
            logs[target].write(f"# Summary: Sent={s['sent']}, Received={s['received']}, Loss={loss:.1f}%\n")
            logs[target].close()

    return completed
