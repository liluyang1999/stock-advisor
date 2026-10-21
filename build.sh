#!/usr/bin/env bash
# Windows Git Bash only: the package entry validates the supported platform.
set -euo pipefail
cd "$(dirname "$0")"
python -B scripts/package_app.py "$@"
