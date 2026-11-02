#!/usr/bin/env python
"""
Daemonizing launcher for the FarmIntel backend.

Detaches uvicorn into its own session so it keeps running after the
terminal that started it closes. The port comes from BACKEND_PORT.

Usage:
    python serve.py            # start (if not already running)
    python serve.py --status   # show whether the port is serving
"""
import os
import socket
import sys
import urllib.request

from config import settings

VENV_PY = sys.executable  # run with the collab venv python
PORT = settings.backend_port


def port_open() -> bool:
    with socket.socket() as s:
        s.settimeout(1)
        return s.connect_ex(("127.0.0.1", PORT)) == 0


def health() -> str:
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{PORT}/health", timeout=5) as r:
            return r.read().decode()
    except Exception as e:  # noqa: BLE001
        return f"health check failed: {e}"


def start():
    if port_open():
        print(f"Already serving on :{PORT}")
        print(health())
        return

    log = open("/tmp/farmintel_backend.log", "ab")
    log.write(f"\n=== serve.py start {os.getpid()} ===\n".encode())
    log.flush()

    # Double-fork daemonize so the server survives the parent shell
    if os.fork() > 0:
        return  # parent returns immediately
    os.setsid()
    if os.fork() > 0:
        os._exit(0)
    os.dup2(log.fileno(), 1)
    os.dup2(log.fileno(), 2)
    log.close()

    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    os.execv(VENV_PY, [VENV_PY, "-m", "uvicorn", "main:app",
                       "--host", "0.0.0.0", "--port", str(PORT)])


if __name__ == "__main__":
    if "--status" in sys.argv:
        print("UP" if port_open() else "DOWN")
        if port_open():
            print(health())
    else:
        start()
        # Give the daemon a moment, then report
        import time
        for _ in range(30):
            if port_open():
                print(f"✅ Backend serving on :{PORT}")
                print(health())
                break
            time.sleep(1)
        else:
            print("❌ Server did not come up; see /tmp/farmintel_backend.log")
            sys.exit(1)
