#!/data/data/com.termux/files/usr/bin/bash
# Compatibilidad: el instalador real vive en install.sh (raíz del repo).
#
# Uso:
#   bash deploy/phone-install.sh

set -euo pipefail

DEST="${BOT_DIR:-$HOME/bot-tracker}"
INSTALLER="$DEST/install.sh"

if [ ! -f "$INSTALLER" ]; then
    INSTALLER="$(cd "$(dirname "$0")/.." && pwd)/install.sh"
fi

[ -f "$INSTALLER" ] || {
    echo "❌ No encuentro install.sh. Clona el repo o usa el instalador remoto." >&2
    exit 1
}

exec bash "$INSTALLER" "$@"
