#!/usr/bin/env python3
"""EnviroMesh Core (RPi 2) Health Check Script.

Checks:
  1. Central EMQX MQTT TLS port (8883) & plain port (1883)
  2. TimescaleDB container liveness
  3. FastAPI backend /health endpoint
  4. Nginx reverse proxy & React Dashboard HTTP response
  5. Recent telemetry ingestion record in PostgreSQL
"""

import json
import os
import socket
import subprocess
import sys
import urllib.request
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent / "raspberry_pi" / "core"


def check_port(host: str, port: int, timeout: float = 3.0) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except (socket.timeout, ConnectionRefusedError, OSError):
        return False


def check_http_endpoint(url: str, timeout: float = 3.0):
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            return response.status, response.read().decode("utf-8")
    except Exception as e:
        return None, str(e)


def check_docker_containers():
    try:
        res = subprocess.run(
            ["docker", "compose", "-f", str(BASE_DIR / "docker-compose.yml"), "ps", "--format", "{{.Name}}: {{.Status}}"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        return res.stdout.strip() if res.returncode == 0 else "Docker compose check failed"
    except Exception as e:
        return f"Docker check unavailable ({e})"


def check_database_telemetry():
    try:
        cmd = [
            "docker", "compose", "-f", str(BASE_DIR / "docker-compose.yml"),
            "exec", "-T", "timescaledb",
            "psql", "-U", "enviromesh_app", "-d", "enviromesh", "-t", "-c",
            "SELECT device_id, timestamp, gateway_id FROM sensor_telemetry ORDER BY timestamp DESC LIMIT 1;"
        ]
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
        if res.returncode == 0 and res.stdout.strip():
            return f"OK (Latest: {res.stdout.strip()})"
        return "NO DATA / QUERY FAILED"
    except Exception as e:
        return f"DB check failed ({e})"


def main():
    print("=" * 60)
    print(" EnviroMesh RPi 2 (Core) Health Check")
    print("=" * 60)

    # 1. EMQX ports
    tls_up = check_port("127.0.0.1", 8883)
    tcp_up = check_port("127.0.0.1", 1883)
    dash_up = check_port("127.0.0.1", 18083)
    print(f"[*] Central EMQX TLS (:8883):          {'UP' if tls_up else 'DOWN'}")
    print(f"[*] Central EMQX TCP (:1883):          {'UP' if tcp_up else 'DOWN'}")
    print(f"[*] Central EMQX Dashboard (:18083):    {'UP' if dash_up else 'DOWN'}")

    # 2. FastAPI Backend
    status, body = check_http_endpoint("http://127.0.0.1:8000/health")
    if status == 200:
        print(f"[*] FastAPI /health:                   UP (HTTP 200: {body.strip()})")
    else:
        # Check via Nginx proxy
        status_proxy, _ = check_http_endpoint("http://127.0.0.1:8080/api/health")
        if status_proxy == 200:
            print("[*] FastAPI (via Nginx proxy):         UP (HTTP 200)")
        else:
            print(f"[*] FastAPI /health:                   DOWN ({body})")

    # 3. Nginx / Dashboard
    status_dash, _ = check_http_endpoint("http://127.0.0.1:8080/")
    print(f"[*] Nginx / Web Dashboard (:8080):     {'UP (HTTP 200)' if status_dash == 200 else 'DOWN'}")

    # 4. Database Telemetry
    db_status = check_database_telemetry()
    print(f"[*] TimescaleDB Latest Telemetry:       {db_status}")

    # 5. Containers
    print("\n[*] Docker Container Status:")
    print(check_docker_containers())

    print("=" * 60)
    if tls_up and (status == 200 or status_dash == 200):
        print("Summary: Core services operational.")
        return 0
    else:
        print("Summary: Issues detected. Check docker logs.")
        return 1


if __name__ == "__main__":
    sys.exit(main())

