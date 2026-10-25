#!/usr/bin/env python3
"""EnviroMesh — Stack Health Diagnostic Tool.

Performs automated connectivity and health checks across all architectural layers:
1. Reverse Proxy (Nginx on port 8080)
2. Backend REST API (HTTP on port 8080 /api/health)
3. MQTT Broker (EMQX TCP on port 1883)
4. EMQX Web Console (HTTP on port 18083)
5. TimescaleDB (via docker exec pg_isready)

All services are bound to 0.0.0.0 — any device on the same subnet as the RPi
can reach them using the LAN IP printed in the output below.
"""

import os
import socket
import subprocess
import urllib.error
import urllib.request
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
ENV_FILE = ROOT_DIR / ".env"

if ENV_FILE.exists():
    try:
        from dotenv import load_dotenv
        load_dotenv(ENV_FILE)
    except ImportError:
        pass

# Terminal colors
GREEN  = "\033[92m"
RED    = "\033[91m"
YELLOW = "\033[93m"
CYAN   = "\033[96m"
BOLD   = "\033[1m"
RESET  = "\033[0m"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def get_lan_ip() -> str:
    """Return the primary LAN IP of this machine (not 127.0.0.1).

    Connects a UDP socket to an external address; no data is sent, but the OS
    selects the correct outbound interface so we can read its IP.
    """
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


def check_tcp_port(host: str, port: int, timeout: float = 2.0) -> bool:
    """Return True if a TCP port is open and accepting connections."""
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except (socket.timeout, ConnectionRefusedError, OSError):
        return False


def check_http(url: str, timeout: float = 4.0) -> tuple[bool, str]:
    """HTTP GET a URL and return (success, human-readable status)."""
    try:
        req = urllib.request.Request(
            url, headers={"User-Agent": "EnviroMesh-HealthCheck/1.0"}
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            code = resp.getcode()
            return (200 <= code < 400), f"HTTP {code}"
    except urllib.error.HTTPError as exc:
        # 4xx/5xx — port is reachable but app returned an error
        return False, f"HTTP {exc.code}"
    except Exception as exc:
        return False, f"Failed: {exc}"


def check_timescaledb_docker(dbname: str, user: str) -> tuple[bool, str]:
    """Run pg_isready inside the TimescaleDB container via docker exec.

    This avoids any host-port conflicts with a locally installed PostgreSQL.
    """
    try:
        result = subprocess.run(
            [
                "docker", "exec", "enviromesh-timescaledb",
                "pg_isready", "-U", user, "-d", dbname,
            ],
            capture_output=True,
            text=True,
            timeout=6,
        )
        if result.returncode == 0:
            return True, "pg_isready OK (docker exec)"
        output = (result.stdout + result.stderr).strip()
        return False, output or "Not ready"
    except FileNotFoundError:
        return False, "docker not found in PATH"
    except subprocess.TimeoutExpired:
        return False, "Timeout waiting for pg_isready"
    except Exception as exc:
        return False, f"Error: {exc}"


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    print(f"\n{BOLD}{'=' * 58}{RESET}")
    print(f"{BOLD}   EnviroMesh — Stack Health Diagnostics{RESET}")
    print(f"{BOLD}{'=' * 58}{RESET}\n")

    lan_ip         = get_lan_ip()
    web_port       = int(os.getenv("WEB_PORT",              8080))
    mqtt_port      = int(os.getenv("MQTT_PORT",             1883))
    emqx_dash_port = int(os.getenv("EMQX_DASHBOARD_PORT", 18083))
    db_name        = os.getenv("POSTGRES_DB",   "enviromesh")
    db_user        = os.getenv("POSTGRES_USER", "enviromesh_app")

    # All port bindings are 0.0.0.0, so localhost always works for local checks.
    local = "localhost"

    print(f"{CYAN}{BOLD}This machine's LAN IP: {lan_ip}{RESET}")
    print(f"Other devices on the same network can use:\n")
    print(f"  🌐  Dashboard + API : {BOLD}http://{lan_ip}:{web_port}{RESET}")
    print(f"  📡  MQTT Broker     : {BOLD}{lan_ip}:{mqtt_port}{RESET}")
    print(f"  🛠   EMQX Console    : {BOLD}http://{lan_ip}:{emqx_dash_port}{RESET}\n")

    checks: list[tuple[str, str, bool, str]] = []

    # 1. Nginx reverse proxy (serves dashboard + /api/*)
    ok, msg = check_http(f"http://{local}:{web_port}")
    checks.append(("Nginx Gateway (Proxy)", f"{local}:{web_port}", ok, msg))

    # 2. Backend via Nginx proxy (/api/health)
    ok, msg = check_http(f"http://{local}:{web_port}/api/health")
    checks.append(("FastAPI Backend (/api/health)", f"{local}:{web_port}/api", ok, msg))

    # 3. EMQX MQTT broker — bound to 0.0.0.0, reachable from LAN
    ok_mqtt = check_tcp_port(local, mqtt_port)
    checks.append((
        "EMQX MQTT Broker",
        f"{local}:{mqtt_port}",
        ok_mqtt,
        f"Port open — LAN clients: {lan_ip}:{mqtt_port}" if ok_mqtt else "Connection Refused",
    ))

    # 4. EMQX web console — bound to 0.0.0.0, reachable from LAN
    ok_dash = check_tcp_port(local, emqx_dash_port)
    checks.append((
        "EMQX Web Console",
        f"{local}:{emqx_dash_port}",
        ok_dash,
        f"Open — http://{lan_ip}:{emqx_dash_port}" if ok_dash else "Connection Refused",
    ))

    # 5. TimescaleDB — internal to Docker; check via docker exec
    ok_db, msg_db = check_timescaledb_docker(db_name, db_user)
    checks.append(("TimescaleDB Database", f"docker:5432/{db_name}", ok_db, msg_db))

    # -----------------------------------------------------------------------
    # Print results table
    # -----------------------------------------------------------------------
    col_svc    = 30
    col_target = 26
    col_status = 8
    total_width = col_svc + col_target + col_status + 40

    print(f"{'SERVICE':<{col_svc}} | {'TARGET':<{col_target}} | {'STATUS':<{col_status}} | DETAILS")
    print("-" * total_width)

    all_passed = True
    for service, target, ok, details in checks:
        colour = GREEN if ok else RED
        status_word = "ONLINE" if ok else "OFFLINE"
        # ANSI codes are invisible characters — pad before adding colour
        status_str = f"{colour}{status_word}{RESET}"
        # Compensate for invisible ANSI bytes so columns line up
        ansi_pad = len(colour) + len(RESET)
        print(
            f"{service:<{col_svc}} | {target:<{col_target}} | "
            f"{status_str:<{col_status + ansi_pad}} | {details}"
        )
        if not ok:
            all_passed = False

    print("-" * total_width)
    if all_passed:
        print(f"\n{GREEN}{BOLD}✔ All EnviroMesh core services are running normally!{RESET}\n")
    else:
        print(f"\n{YELLOW}{BOLD}⚠  Some services are currently unreachable.{RESET}")
        print("  • Docker stack not running?  →  ./scripts/docker_control.sh start")
        print("  • Backend 502 Bad Gateway?   →  ./scripts/docker_control.sh build")
        print("  •                                ./scripts/docker_control.sh restart")
        print("  • TimescaleDB not ready?     →  Container may still be initializing.\n")


if __name__ == "__main__":
    main()
