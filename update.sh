#!/data/data/com.termux/files/usr/bin/bash
# Lanzador corto para actualizar el bot en Termux.
#
# Uso:
#   bash ~/bot-tracker/update.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
exec bash "$SCRIPT_DIR/deploy/termux-update.sh" "$@"
