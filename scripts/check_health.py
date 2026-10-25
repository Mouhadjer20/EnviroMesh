#!/usr/bin/env python3
"""EnviroMesh — Stack Health Diagnostic Tool.

Performs automated connectivity and health checks across all architectural layers:
1. Reverse Proxy (Nginx on port 8080)
2. Web Dashboard (HTTP on port 8080 /)
3. Backend REST API (HTTP on port 8080 /api/health or 8000 /health)
4. MQTT Broker (EMQX TCP on port 1883)
5. TimescaleDB (PostgreSQL TCP / authentication on port 5432)
"""

import os
from pathlib import Path
import socket
import sys
import urllib.error
import urllib.request

ROOT_DIR = Path(__file__).resolve().parents[1]
ENV_FILE = ROOT_DIR / ".env"

if ENV_FILE.exists():
    try:
        from dotenv import load_dotenv
        load_dotenv(ENV_FILE)
    except ImportError:
        pass

# Terminal colors
GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
BOLD = "\033[1m"
RESET = "\033[0m"


def check_tcp_port(host: str, port: int, timeout: float = 2.0) -> bool:
    """Test if a TCP port is open and listening."""
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except (socket.timeout, ConnectionRefusedError, OSError):
        return False


def check_http_endpoint(url: str, timeout: float = 3.0) -> tuple[bool, str]:
    """Test HTTP GET endpoint and return (success, status_msg)."""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "EnviroMesh-HealthCheck/1.0"})
        with urllib.request.urlopen(req, timeout=timeout) as response:
            status = response.getcode()
            if 200 <= status < 400:
                return True, f"HTTP {status}"
            return False, f"HTTP {status}"
    except urllib.error.HTTPError as exc:
        return False, f"HTTP {exc.code}"
    except Exception as exc:
        return False, f"Failed: {exc}"


def check_timescaledb(host: str, port: int, dbname: str, user: str, password: str) -> tuple[bool, str]:
    """Check TimescaleDB connectivity via psycopg2 if available, else TCP socket."""
    try:
        import psycopg2
        conn = psycopg2.connect(
            host=host,
            port=port,
            dbname=dbname,
            user=user,
            password=password,
            connect_timeout=3,
        )
        with conn.cursor() as cur:
            cur.execute("SELECT version(), extversion FROM pg_extension WHERE extname = 'timescaledb';")
            row = cur.fetchone()
            tsdb_ver = row[1] if row else "not active"
        conn.close()
        return True, f"OK (TimescaleDB {tsdb_ver})"
    except ImportError:
        # Fallback to TCP socket check
        if check_tcp_port(host, port):
            return True, "TCP Port Open (psycopg2 not installed for deep check)"
        return False, "TCP Connection Refused"
    except Exception as exc:
        return False, f"Auth/Query Error: {exc}"


def main():
    print(f"\n{BOLD}======================================================{RESET}")
    print(f"{BOLD}   EnviroMesh — Stack Health Diagnostics              {RESET}")
    print(f"{BOLD}======================================================{RESET}\n")

    web_host = "localhost"
    web_port = int(os.getenv("WEB_PORT", 8080))
    api_port = int(os.getenv("API_PORT", 8000))
    mqtt_host = os.getenv("MQTT_HOST", "localhost")
    if mqtt_host == "emqx":
        mqtt_host = "localhost"
    mqtt_port = int(os.getenv("MQTT_PORT", 1883))
    emqx_dash_port = int(os.getenv("EMQX_DASHBOARD_PORT", 18083))

    db_host = os.getenv("DB_HOST", "localhost")
    if db_host == "timescaledb":
        db_host = "localhost"
    db_port = int(os.getenv("DB_PORT", 5432))
    db_name = os.getenv("POSTGRES_DB", "enviromesh")
    db_user = os.getenv("POSTGRES_USER", "enviromesh_app")
    db_password = os.getenv("POSTGRES_PASSWORD", "")

    checks = []

    # 1. Nginx Reverse Proxy
    url_proxy = f"http://{web_host}:{web_port}"
    ok, msg = check_http_endpoint(url_proxy)
    checks.append(("Nginx Gateway (Proxy)", f"{web_host}:{web_port}", ok, msg))

    # 2. Backend Health (Direct or via Proxy)
    url_api = f"http://{web_host}:{web_port}/api/health"
    ok, msg = check_http_endpoint(url_api)
    if not ok:
        # Try direct
        url_api_direct = f"http://localhost:{api_port}/health"
        ok, msg = check_http_endpoint(url_api_direct)
        checks.append(("FastAPI Backend (/health)", f"localhost:{api_port}", ok, msg))
    else:
        checks.append(("FastAPI Backend (/api/health)", f"{web_host}:{web_port}/api", ok, msg))

    # 3. MQTT Broker (EMQX)
    ok_mqtt = check_tcp_port(mqtt_host, mqtt_port)
    msg_mqtt = "Port 1883 Open" if ok_mqtt else "Connection Refused"
    checks.append(("EMQX MQTT Broker", f"{mqtt_host}:{mqtt_port}", ok_mqtt, msg_mqtt))

    # 4. EMQX Dashboard
    ok_emqx_dash = check_tcp_port(mqtt_host, emqx_dash_port)
    msg_emqx_dash = "Port 18083 Open" if ok_emqx_dash else "Connection Refused"
    checks.append(("EMQX Web Console", f"{mqtt_host}:{emqx_dash_port}", ok_emqx_dash, msg_emqx_dash))

    # 5. TimescaleDB
    ok_db, msg_db = check_timescaledb(db_host, db_port, db_name, db_user, db_password)
    checks.append(("TimescaleDB Database", f"{db_host}:{db_port}/{db_name}", ok_db, msg_db))

    # Print results table
    print(f"{'SERVICE':<28} | {'TARGET':<22} | {'STATUS':<8} | {'DETAILS'}")
    print("-" * 80)

    all_passed = True
    for service, target, ok, details in checks:
        if ok:
            status = f"{GREEN}ONLINE{RESET}"
        else:
            status = f"{RED}OFFLINE{RESET}"
            all_passed = False
        print(f"{service:<28} | {target:<22} | {status:<17} | {details}")

    print("\n" + "-" * 80)
    if all_passed:
        print(f"{GREEN}{BOLD}✔ All EnviroMesh core services are running normally!{RESET}\n")
    else:
        print(f"{YELLOW}{BOLD}⚠ Some services are currently unreachable.{RESET}")
        print("  • If using Docker: run './scripts/docker_control.sh start'")
        print("  • If using local services: verify EMQX and PostgreSQL are running.\n")


if __name__ == "__main__":
    main()
