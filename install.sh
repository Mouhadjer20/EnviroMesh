#!/usr/bin/env bash
# ==============================================================================
# EnviroMesh — Root Installation & Setup Entrypoint
# ==============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec bash "${SCRIPT_DIR}/scripts/setup_env.sh" "$@"

