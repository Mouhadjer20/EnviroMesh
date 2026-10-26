#!/usr/bin/env python3
"""EnviroMesh — LoRa Packet Injector / Test Harness.

Tests the LoRa packet processing pipeline without needing a physical SX1278 radio.
Simulates raw LoRa payload reception and passes it through the exact parser,
validator, and TimescaleDB writer functions used by backend/services/lora_receiver.py.
"""

import argparse
from datetime import datetime, timezone
import json
import logging
import os
from pathlib import Path
import sys

ROOT_DIR = Path(__file__).resolve().parents[1]
BACKEND_DIR = ROOT_DIR / "raspberry_pi" / "backend"

sys.path.insert(0, str(BACKEND_DIR))

# Load .env
ENV_FILE = ROOT_DIR / ".env"
if ENV_FILE.exists():
    try:
        from dotenv import load_dotenv
        load_dotenv(ENV_FILE)
    except ImportError:
        pass

try:
    from services.colored_logger import setup_colored_logging
    logger = setup_colored_logging(name="lora_injector")
except ImportError:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    logger = logging.getLogger("lora_injector")

try:
    from services.telemetry_validator import validate
    from services.database_writer import write_telemetry, write_raw_packet
except ImportError as exc:
    logger.error("Could not import backend services: %s", exc)
    logger.info("Make sure dependencies are installed: pip install psycopg2-binary python-dotenv")
    sys.exit(1)


def inject_lora_packet(raw_payload: str, device_id: str = "G11"):
    """Replicates process_packet from services/lora_receiver.py."""
    logger.info("Injecting raw LoRa packet for device %s...", device_id)
    parsed = False
    telemetry = None

    try:
        telemetry = json.loads(raw_payload)
        parsed = True
    except (json.JSONDecodeError, TypeError) as exc:
        logger.warning("LoRa packet is not valid JSON: %s (error: %s)", raw_payload, exc)

    extracted_device = telemetry.get("device_id") if isinstance(telemetry, dict) else device_id
    write_raw_packet(extracted_device, "LoRa", raw_payload.encode("utf-8"), parsed)
    logger.info("✔ Raw packet logged into 'raw_sensor_packets' hypertable (parsed=%s)", parsed)

    if not parsed:
        logger.error("✖ Processing stopped: JSON parsing failed.")
        return False

    if not validate(telemetry):
        logger.warning("✖ Telemetry failed validation: %s", telemetry)
        return False

    write_telemetry(telemetry)
    logger.info("✔ Telemetry passed validation and written to 'sensor_telemetry' hypertable!")
    return True


def main():
    parser = argparse.ArgumentParser(
        description="EnviroMesh LoRa Packet Injector",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--device", default="G11", choices=["G11", "G41"], help="Target device ID")
    parser.add_argument("--gas", type=float, default=45.2, help="Gas ppm value")
    parser.add_argument("--temp", type=float, default=24.5, help="Temperature in °C")
    parser.add_argument("--humidity", type=float, default=58.0, help="Humidity percentage")
    parser.add_argument("--water", type=int, choices=[0, 1], default=0, help="Water leak state (0=Dry, 1=Leak)")
    parser.add_argument("--corrupt-json", action="store_true", help="Send malformed JSON to test error handling")

    args = parser.parse_args()

    if args.corrupt_json:
        payload_str = "{bad_json: missing_quotes, raw_data_gibberish}"
    else:
        sample_doc = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "device_id": args.device,
            "group_code": "G1" if args.device == "G11" else "G4",
            "zone": "Sector_A_Warehouse" if args.device == "G11" else "Sector_B_Warehouse",
            "protocol": "LoRa",
            "metrics": {
                "gas_ppm": args.gas,
                "temperature_c": args.temp,
                "humidity": args.humidity,
                "water_leak": args.water,
            },
            "metadata": {
                "injected_via": "lora_packet_inject.py",
                "firmware_version": "1.0.0",
            },
            "rssi": -74,
        }
        payload_str = json.dumps(sample_doc)

    print(f"\nPayload to inject:\n{payload_str}\n")
    inject_lora_packet(payload_str, args.device)


if __name__ == "__main__":
    main()
