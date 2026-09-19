"""Test Uvicorn graceful shutdown on SIGTERM."""
import os
import signal
import subprocess
import sys
import time
import urllib.request
from threading import Thread

def main():
    print("[TEST] Launching Uvicorn subprocess...")
    env = {**os.environ, "DATABASE_URL": "sqlite:///./test.db", "PYTHONPATH": "backend"}
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8899", "--timeout-graceful-shutdown", "5"],
        cwd="backend",
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    try:
        # Wait for server to become responsive
        started = False
        for _ in range(30):
            try:
                res = urllib.request.urlopen("http://127.0.0.1:8899/health/live", timeout=1)
                if res.status == 200:
                    started = True
                    break
            except Exception:
                time.sleep(0.2)

        if not started:
            raise RuntimeError("Uvicorn failed to start within timeout")
        print("[TEST] Uvicorn is healthy and serving requests.")

        # Send an in-flight request in background thread
        results = []
        def make_request():
            try:
                r = urllib.request.urlopen("http://127.0.0.1:8899/health/ready", timeout=5)
                results.append(r.status)
            except Exception as e:
                results.append(e)

        t = Thread(target=make_request)
        t.start()

        # Send SIGTERM to process while request is in flight
        time.sleep(0.05)
        print("[TEST] Sending SIGTERM to Uvicorn process...")
        proc.send_signal(signal.SIGTERM)

        # Wait for thread to finish
        t.join(timeout=4)
        exit_code = proc.wait(timeout=5)

        print(f"[TEST] Request completed with result: {results}")
        print(f"[TEST] Process terminated with exit code: {exit_code}")

        assert results == [200], f"Expected [200], got {results}"
        assert exit_code in (0, -signal.SIGTERM, 143), f"Expected graceful exit, got {exit_code}"
        print("=== GRACEFUL SHUTDOWN VERIFICATION SUCCESSFUL ===")
    finally:
        if proc.poll() is None:
            proc.kill()

if __name__ == "__main__":
    main()
