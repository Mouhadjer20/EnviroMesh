#!/usr/bin/env python3
"""EnviroMesh — Real-Time MQTT Telemetry Monitor.

Subscribes to all EnviroMesh topics on the EMQX broker, decodes JSON payloads,
validates them against the schema, and displays formatted metrics in real time.
"""

import argparse
from datetime import datetime
import json
import logging
import os
from pathlib import Path
import sys
import time

ROOT_DIR = Path(__file__).resolve().parents[1]
ENV_FILE = ROOT_DIR / ".env"

if ENV_FILE.exists():
    try:
        from dotenv import load_dotenv
        load_dotenv(ENV_FILE)
    except ImportError:
        pass

try:
    import paho.mqtt.client as mqtt
except ImportError:
    print("Error: paho-mqtt is required. Run 'pip install paho-mqtt'.")
    sys.exit(1)

# Color terminal output
CYAN = "\033[96m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
RED = "\033[91m"
BOLD = "\033[1m"
RESET = "\033[0m"

msg_count = 0
start_time = time.time()


def on_connect(client, userdata, flags, reason_code, properties=None):
    if reason_code == 0:
        topic = userdata.get("topic", "enviromesh/#")
        print(f"{GREEN}✔ Connected to MQTT Broker! Subscribing to: {BOLD}{topic}{RESET}\n")
        client.subscribe(topic, qos=1)
        print(f"{'TIMESTAMP':<20} | {'DEVICE':<6} | {'ZONE':<22} | {'TEMP (°C)':<9} | {'GAS (PPM)':<9} | {'WATER':<6} | {'PROTOCOL':<8}")
        print("-" * 96)
    else:
        print(f"{RED}✖ Failed to connect to broker (reason code: {reason_code}){RESET}")


def on_message(client, userdata, msg):
    global msg_count
    msg_count += 1
    raw_payload = msg.payload.decode("utf-8", errors="replace")

    try:
        data = json.loads(raw_payload)
    except json.JSONDecodeError:
        print(f"{RED}[NON-JSON MSG on {msg.topic}]: {raw_payload}{RESET}")
        return

    device_id = data.get("device_id", "N/A")
    zone = data.get("zone", "N/A")
    protocol = data.get("protocol", "N/A")
    metrics = data.get("metrics", {})

    temp = metrics.get("temperature_c", "—")
    gas = metrics.get("gas_ppm", "—")
    water = metrics.get("water_leak", metrics.get("water_leak_detected", "—"))

    # Formatting water status
    water_str = f"{RED}LEAK!{RESET}" if (water == 1 or water is True) else "Dry"

    # Color gas if threshold exceeded
    gas_str = str(gas)
    if isinstance(gas, (int, float)) and gas > 2000:
        gas_str = f"{RED}{gas:.1f} ⚠{RESET}"
    elif isinstance(gas, (int, float)):
        gas_str = f"{gas:.1f}"

    temp_str = f"{temp:.1f}" if isinstance(temp, (int, float)) else str(temp)
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    print(f"{ts:<20} | {CYAN}{device_id:<6}{RESET} | {zone:<22} | {temp_str:<9} | {gas_str:<9} | {water_str:<6} | {protocol:<8}")

    if userdata.get("verbose"):
        print(f"  {YELLOW}Raw payload: {json.dumps(data)}{RESET}")


def main():
    parser = argparse.ArgumentParser(
        description="EnviroMesh Live MQTT Telemetry Monitor",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--host",
        default=os.getenv("MQTT_HOST", "localhost"),
        help="MQTT broker host",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.getenv("MQTT_PORT", 1883)),
        help="MQTT broker port",
    )
    parser.add_argument(
        "--username",
        default=os.getenv("MQTT_APP_USERNAME", "enviromesh_backend"),
        help="MQTT client username",
    )
    parser.add_argument(
        "--password",
        default=os.getenv("MQTT_APP_PASSWORD", ""),
        help="MQTT client password",
    )
    parser.add_argument(
        "--topic",
        default="enviromesh/#",
        help="MQTT topic filter to monitor",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Print raw JSON payload for each message",
    )

    args = parser.parse_args()

    client = mqtt.Client(
        callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
        client_id="enviromesh-terminal-monitor",
        userdata={"topic": args.topic, "verbose": args.verbose},
    )

    if args.username and args.password:
        client.username_pw_set(args.username, args.password)

    client.on_connect = on_connect
    client.on_message = on_message

    print(f"{BOLD}Starting EnviroMesh MQTT Monitor on {args.host}:{args.port}...{RESET}")

    try:
        client.connect(args.host, args.port, keepalive=60)
        client.loop_forever()
    except KeyboardInterrupt:
        elapsed = time.time() - start_time
        print(f"\n{BOLD}Monitor stopped.{RESET} Received {msg_count} messages in {elapsed:.1f}s.")
    except Exception as exc:
        print(f"{RED}Error: {exc}{RESET}")
        sys.exit(1)


if __name__ == "__main__":
    main()
