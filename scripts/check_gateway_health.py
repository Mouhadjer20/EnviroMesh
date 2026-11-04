#!/usr/bin/env python3
"""EnviroMesh Gateway (RPi 1) Health Check Script.

Checks:
  1. Local EMQX MQTT broker connectivity and port binding
  2. Gateway container status
  3. SQLite offline queue depth and database integrity
  4. Core RPi 2 TLS port reachability
  5. SPI hardware device availability (/dev/spidev0.0)
"""

import os
import socket
import sqlite3
import subprocess
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent / "raspberry_pi" / "gateway"


def check_port(host: str, port: int, timeout: float = 3.0) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except (socket.timeout, ConnectionRefusedError, OSError):
        return False


def check_sqlite_queue():
    db_path = BASE_DIR / "data" / "queue.db"
    # Also check typical container volume path if running on host
    if not db_path.exists():
        alt_path = Path("/var/lib/enviromesh/queue.db")
        if alt_path.exists():
            db_path = alt_path

    if not db_path.exists():
        return "UNKNOWN (queue.db not found on host filesystem)"

    try:
        conn = sqlite3.connect(str(db_path))
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM queue")
        count = cur.fetchone()[0]
        cur.execute("SELECT attempts FROM queue ORDER BY attempts DESC LIMIT 1")
        max_attempts = cur.fetchone()
        max_att = max_attempts[0] if max_attempts else 0
        conn.close()
        return f"OK ({count} pending messages, max attempts: {max_att})"
    except Exception as e:
        return f"ERROR ({e})"


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


def main():
    print("=" * 60)
    print(" EnviroMesh RPi 1 (Gateway) Health Check")
    print("=" * 60)

    # 1. Local MQTT
    local_mqtt = check_port("127.0.0.1", 1883)
    print(f"[*] Local EMQX (127.0.0.1:1883):       {'UP' if local_mqtt else 'DOWN'}")

    # 2. Local EMQX Dashboard
    local_dash = check_port("127.0.0.1", 18083)
    print(f"[*] Local EMQX Dashboard (:18083):    {'UP' if local_dash else 'DOWN'}")

    # 3. SPI Hardware
    spi_exists = os.path.exists("/dev/spidev0.0")
    print(f"[*] SX1278 SPI Device (/dev/spidev0.0): {'PRESENT' if spi_exists else 'NOT DETECTED (Fallback mode)'}")

    # 4. SQLite Queue
    q_status = check_sqlite_queue()
    print(f"[*] SQLite Offline Queue:               {q_status}")

    # 5. Core RPi 2 Reachability
    core_host = os.getenv("MQTT_CORE_HOST", "192.168.1.5")
    core_port = int(os.getenv("MQTT_CORE_PORT", "8883"))
    core_reachable = check_port(core_host, core_port)
    print(f"[*] Core RPi 2 TLS Port ({core_host}:{core_port}): {'REACHABLE' if core_reachable else 'UNREACHABLE'}")

    # 6. Containers
    print("\n[*] Docker Container Status:")
    print(check_docker_containers())

    print("=" * 60)
    if local_mqtt:
        print("Summary: Gateway base services operational.")
        return 0
    else:
        print("Summary: Issues detected. Check docker logs.")
        return 1


if __name__ == "__main__":
    sys.exit(main())

