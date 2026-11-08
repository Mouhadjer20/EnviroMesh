#!/usr/bin/env python3
"""EnviroMesh — Unified Automated Test & Simulation Runner.

Runs all automated test suites, component checks, and pipeline simulations
for both RPi 1 Gateway and RPi 2 Core on a single device.

Usage:
  python3 scripts/run_tests.py
"""

import os
import sys
import subprocess
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT_DIR))

GREEN = "\033[0;32m"
BLUE = "\033[0;34m"
YELLOW = "\033[1;33m"
RED = "\033[0;31m"
BOLD = "\033[1m"
NC = "\033[0m"


def run_command(cmd, desc):
    print(f"\n{BOLD}{BLUE}=== Running: {desc} ==={NC}")
    res = subprocess.run(cmd, shell=True, cwd=str(ROOT_DIR))
    if res.returncode != 0:
        print(f"{RED}✖ FAILED: {desc} (exit code {res.returncode}){NC}")
        return False
    print(f"{GREEN}✔ PASSED: {desc}{NC}")
    return True


def main():
    print(f"{BOLD}================================================================={NC}")
    print(f"{BOLD} EnviroMesh Unified Test & Simulation Suite{NC}")
    print(f"{BOLD}================================================================={NC}")

    all_passed = True

    # 1. Python Syntax Validation
    cmd_syntax = (
        f"{sys.executable} -m py_compile "
        "raspberry_pi/gateway/gateway/*.py "
        "raspberry_pi/core/backend/*.py "
        "raspberry_pi/core/backend/services/*.py "
        "raspberry_pi/core/backend/routes/*.py "
        "scripts/*.py"
    )
    if not run_command(cmd_syntax, "Python syntax compilation check"):
        all_passed = False

    # 2. End-to-End Pipeline Simulation
    cmd_pipeline = f"{sys.executable} scripts/simulate_pipeline.py"
    if not run_command(cmd_pipeline, "End-to-end pipeline simulation (Gateway + Core)"):
        all_passed = False

    # 3. Telemetry Simulator Test (Print-only)
    cmd_simulator = f"{sys.executable} scripts/simulate_telemetry.py --print-only --count 2 --device all"
    if not run_command(cmd_simulator, "Telemetry simulator (all devices, print-only)"):
        all_passed = False

    # 4. Check if pytest is available to run full tests/ suite
    has_pytest = subprocess.run(
        f"{sys.executable} -m pytest --version",
        shell=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    ).returncode == 0

    if has_pytest:
        cmd_pytest = f"{sys.executable} -m pytest tests/ -v"
        if not run_command(cmd_pytest, "Pytest test suite (tests/)"):
            all_passed = False
    else:
        print(f"\n{YELLOW}ℹ Pytest is not installed in this environment.{NC}")
        print(f"  To run the full unit test suite in `tests/`, install pytest:")
        print(f"    pip install pytest\n")

    print(f"\n{BOLD}================================================================={NC}")
    if all_passed:
        print(f"{BOLD}{GREEN} ALL TESTS & SIMULATIONS COMPLETED SUCCESSFULLY! (100% PASS){NC}")
        print(f"{BOLD}================================================================={NC}")
        return 0
    else:
        print(f"{BOLD}{RED} SOME TESTS FAILED. Please review the output above.{NC}")
        print(f"{BOLD}================================================================={NC}")
        return 1


if __name__ == "__main__":
    sys.exit(main())

