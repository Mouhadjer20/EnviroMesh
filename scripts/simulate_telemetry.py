#!/usr/bin/env python3
"""EnviroMesh — Telemetry Simulator.

Simulates environmental field nodes (G11, G41, G31, G61) sending realistic
sensor telemetry over MQTT to the EMQX broker or directly to TimescaleDB.

Useful for:
- Testing the MQTT subscriber and TimescaleDB ingestion pipeline without hardware.
- Stress testing the API and database with continuous streams.
- Simulating emergency scenarios (gas leaks, temperature spikes, water leaks).
"""

import argparse
from datetime import datetime, timezone
import json
import logging
import os
from pathlib import Path
import random
import sys
import time

# Try loading .env from project root
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
    mqtt = None

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("telemetry_simulator")

# Device Profiles
DEVICE_PROFILES = {
    "G11": {
        "group_code": "G1",
        "zone": "Sector_A_Warehouse",
        "protocol": "lora",
        "sensors": ["MQ-2", "DHT11", "Water Sensor"],
    },
    "G41": {
        "group_code": "G4",
        "zone": "Sector_B_Warehouse",
        "protocol": "lora",
        "sensors": ["MQ-2", "DHT11", "Water Sensor"],
    },
    "G31": {
        "group_code": "G3",
        "zone": "Sector_C_Utility_Room",
        "protocol": "wifi_mqtt",
        "sensors": ["BMP280", "MQ-2", "Water Sensor"],
    },
    "G61": {
        "group_code": "G6",
        "zone": "Sector_A_Valve",
        "protocol": "wifi_mqtt",
        "sensors": ["MQ-2", "DHT11", "Water Sensor", "PIR"],
    },
}


def generate_reading(device_id: str, anomaly: str = "none") -> dict:
    """Generate a realistic telemetry payload adhering to EnviroMesh schema."""
    profile = DEVICE_PROFILES.get(device_id, DEVICE_PROFILES["G11"])
    now_iso = datetime.now(timezone.utc).isoformat()

    # Normal baseline readings
    gas_ppm = round(random.uniform(20.0, 80.0), 1)
    temperature_c = round(random.uniform(21.0, 26.5), 1)
    humidity_pct = round(random.uniform(45.0, 65.0), 1)
    pressure_hpa = round(random.uniform(1010.0, 1015.0), 2)
    water_leak = 0
    motion_detected = 0

    # Apply anomalies if requested
    if anomaly == "gas_leak":
        gas_ppm = round(random.uniform(2500.0, 6000.0), 1)
    elif anomaly == "fire_temp":
        temperature_c = round(random.uniform(65.0, 82.0), 1)
        gas_ppm = round(random.uniform(800.0, 2200.0), 1)
    elif anomaly == "water_leak":
        water_leak = 1
    elif anomaly == "motion":
        motion_detected = 1

    metrics = {}

    # Populate metrics according to sensor set
    sensors = profile["sensors"]
    if "MQ-2" in sensors:
        metrics["gas_ppm"] = gas_ppm
        metrics["smoke_detected"] = gas_ppm > 2000.0
    if "DHT11" in sensors:
        metrics["temperature_c"] = temperature_c
        metrics["humidity"] = humidity_pct
    if "BMP280" in sensors:
        metrics["pressure_hpa"] = pressure_hpa
        metrics["temperature_c"] = temperature_c
    if "Water Sensor" in sensors:
        metrics["water_leak"] = water_leak
    if "PIR" in sensors:
        metrics["motion_detected"] = motion_detected

    payload = {
        "timestamp": now_iso,
        "device_id": device_id,
        "group_code": profile["group_code"],
        "zone": profile["zone"],
        "protocol": profile["protocol"],
        "metrics": metrics,
        "metadata": {
            "firmware_version": "1.0.0",
            "simulated": True,
            "anomaly_mode": anomaly,
        },
        "rssi": random.randint(-85, -60),
    }

    return payload


def main():
    parser = argparse.ArgumentParser(
        description="EnviroMesh Synthetic Telemetry Generator",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--device",
        choices=list(DEVICE_PROFILES.keys()) + ["all"],
        default="G11",
        help="Device ID to simulate, or 'all' to cycle through all devices",
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
        "--topic-prefix",
        default="enviromesh/devices",
        help="MQTT topic prefix",
    )
    parser.add_argument(
        "--interval",
        type=float,
        default=2.0,
        help="Interval in seconds between emissions",
    )
    parser.add_argument(
        "--count",
        type=int,
        default=0,
        help="Total messages to emit (0 for infinite loop until Ctrl+C)",
    )
    parser.add_argument(
        "--anomaly",
        choices=["none", "gas_leak", "fire_temp", "water_leak", "motion", "random"],
        default="none",
        help="Inject simulated anomalies into readings",
    )
    parser.add_argument(
        "--print-only",
        action="store_true",
        help="Print generated payloads to stdout without publishing to MQTT",
    )

    args = parser.parse_args()

    client = None
    if not args.print_only:
        if mqtt is None:
            logger.error("paho-mqtt is not installed. Run 'pip install paho-mqtt' or use --print-only.")
            sys.exit(1)

        client = mqtt.Client(
            callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
            client_id=f"enviromesh-simulator-{random.randint(1000, 9999)}",
        )
        if args.username and args.password:
            client.username_pw_set(args.username, args.password)

        logger.info("Connecting to MQTT broker %s:%d...", args.host, args.port)
        try:
            client.connect(args.host, args.port, keepalive=60)
            client.loop_start()
            logger.info("Connected successfully to MQTT broker.")
        except Exception as exc:
            logger.error("Could not connect to MQTT broker (%s:%d): %s", args.host, args.port, exc)
            logger.info("Tip: make sure EMQX is running (./scripts/docker_control.sh start) or run with --print-only.")
            sys.exit(1)

    devices = list(DEVICE_PROFILES.keys()) if args.device == "all" else [args.device]
    sent_count = 0

    logger.info("Starting simulation for device(s): %s (interval=%.1fs, anomaly=%s)", devices, args.interval, args.anomaly)

    try:
        while True:
            for dev_id in devices:
                current_anomaly = args.anomaly
                if current_anomaly == "random":
                    current_anomaly = random.choice(["none", "none", "none", "gas_leak", "water_leak", "motion"])

                reading = generate_reading(dev_id, current_anomaly)
                payload_str = json.dumps(reading, indent=2 if args.print_only else None)
                topic = f"{args.topic_prefix}/{dev_id}/telemetry"

                if args.print_only:
                    print(f"\n--- [Topic: {topic}] ---")
                    print(payload_str)
                else:
                    result = client.publish(topic, payload_str, qos=1)
                    if result.rc == mqtt.MQTT_ERR_SUCCESS:
                        logger.info("Published to %s (gas=%.1f, temp=%.1f, leak=%s, anomaly=%s)",
                                    topic,
                                    reading["metrics"].get("gas_ppm", 0.0),
                                    reading["metrics"].get("temperature_c", 0.0),
                                    reading["metrics"].get("water_leak", 0),
                                    current_anomaly)
                    else:
                        logger.warning("Failed to publish to %s (error code: %s)", topic, result.rc)

                sent_count += 1
                if args.count > 0 and sent_count >= args.count:
                    logger.info("Reached target message count (%d). Exiting.", args.count)
                    return

                time.sleep(args.interval)

    except KeyboardInterrupt:
        logger.info("\nSimulation stopped by user.")
    finally:
        if client:
            client.loop_stop()
            client.disconnect()


if __name__ == "__main__":
    main()
