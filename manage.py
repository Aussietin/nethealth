"""
Management script for the NetHealth application lifecycle.
Supports development, building the frontend, and running in production.
"""
import subprocess
import sys
import os
import signal
import time
from pathlib import Path

def run_dev():
    print("🚀 Starting NetHealth in Development Mode...")
    
    # Start FastAPI backend
    backend_proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "nethealth.api:app", "--reload", "--port", "8000"],
        env={**os.environ, "PYTHONPATH": "."}
    )
    
    # Start Next.js frontend
    frontend_dir = Path("frontend")
    frontend_proc = subprocess.Popen(
        ["npm", "run", "dev"],
        cwd=str(frontend_dir)
    )
    
    def signal_handler(sig, frame):
        print("\n🛑 Stopping servers...")
        backend_proc.terminate()
        frontend_proc.terminate()
        sys.exit(0)
    
    signal.signal(signal.SIGINT, signal_handler)
    
    # Keep the script running
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        signal_handler(None, None)

def build():
    print("🏗️ Building NetHealth Frontend...")
    frontend_dir = Path("frontend")
    
    # Install dependencies if node_modules doesn't exist
    if not (frontend_dir / "node_modules").exists():
        print("📦 Installing frontend dependencies...")
        subprocess.run(["npm", "install"], cwd=str(frontend_dir), check=True)
    
    # Build frontend
    # Note: We need a static export for FastAPI to serve it
    subprocess.run(["npm", "run", "build"], cwd=str(frontend_dir), check=True)
    print("✅ Build complete!")

def run_prod():
    print("🌐 Starting NetHealth in Production Mode...")
    frontend_out = Path("frontend/out")
    if not frontend_out.exists():
        print("❌ Error: Frontend not built. Run 'python manage.py build' first.")
        sys.exit(1)
    
    subprocess.run(
        [sys.executable, "-m", "uvicorn", "nethealth.api:app", "--host", "0.0.0.0", "--port", "8000"],
        env={**os.environ, "PYTHONPATH": "."}
    )

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python manage.py [dev|build|run]")
        sys.exit(1)
        
    cmd = sys.argv[1]
    if cmd == "dev":
        run_dev()
    elif cmd == "build":
        build()
    elif cmd == "run":
        run_prod()
    else:
        print(f"Unknown command: {cmd}")
        sys.exit(1)
