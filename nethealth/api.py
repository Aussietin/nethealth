from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pathlib import Path
import os
import asyncio
from datetime import datetime
from typing import List, Optional

from nethealth.checks.dns import dns_check
from nethealth.checks.ping import ping_check
from nethealth.checks.http import http_check
from nethealth.checks.traceroute import traceroute_check
from nethealth.checks.port import port_check

app = FastAPI(title="NetHealth API")

# Enable CORS for frontend development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/api/health")
async def health():
    """Simple health check endpoint for the API itself."""
    return {"status": "ok"}

@app.get("/api/check/{target}")
async def run_checks(target: str):
    """
    Run a full suite of snapshot diagnostics (DNS, Ping, HTTP, Port) for a target.
    
    Args:
        target (str): The hostname or IP address to check.
    """
    try:
        results = {
            "dns": dns_check(target),
            "ping": ping_check(target),
            "http": http_check(target),
            "port": port_check(target)
        }
        return results
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/traceroute/{target}")
async def run_traceroute(target: str, max_hops: int = 30):
    """
    Run a traceroute diagnostic for a target.
    
    Args:
        target (str): The destination host.
        max_hops (int): Maximum network hops to probe.
    """
    try:
        return traceroute_check(target, max_hops=max_hops)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/port/{target}")
async def run_port_check(target: str, ports: Optional[str] = None):
    """
    Check TCP port reachability for a target.
    
    Args:
        target (str): The host to check.
        ports (str, optional): Comma-separated list of ports.
    """
    try:
        port_list = [int(p.strip()) for p in ports.split(",")] if ports else [22, 80, 443, 8080]
        return port_check(target, ports=port_list)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.websocket("/ws/monitor/{target}")
async def websocket_monitor(websocket: WebSocket, target: str):
    """
    WebSocket endpoint for real-time ping monitoring.
    
    Continuously pings the target and streams results to the client.
    
    Args:
        target (str): The host to monitor.
    """
    await websocket.accept()
    try:
        while True:
            # Reusing the existing ping_check logic
            result = ping_check(target)
            data = {
                "timestamp": datetime.now().strftime("%H:%M:%S"),
                "latency": result.get("avg_ms"),
                "status": result.get("status")
            }
            await websocket.send_json(data)
            await asyncio.sleep(1) # Interval
    except WebSocketDisconnect:
        print(f"Monitor disconnected for {target}")
    except Exception as e:
        error_detail = str(e)
        print(f"Error in monitor: {error_detail}")
        # Send a final error message if possible before closing
        try:
            await websocket.send_json({"status": "fail", "error": error_detail})
        except:
            pass
        await websocket.close(code=1011, reason=error_detail[:120]) # Limit reason length

# Static files for production
frontend_out = Path(__file__).parent.parent / "frontend" / "out"
if frontend_out.exists():
    app.mount("/", StaticFiles(directory=str(frontend_out), html=True), name="frontend")
