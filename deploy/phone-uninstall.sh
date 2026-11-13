#!/data/data/com.termux/files/usr/bin/bash
# Desinstala el servicio del bot y el arranque automático.
#
# Uso:
#   bash deploy/phone-uninstall.sh            # conserva ~/bot-tracker y los datos
#   bash deploy/phone-uninstall.sh --purge    # borra también ~/bot-tracker
#   bash deploy/phone-uninstall.sh --purge --yes

set -euo pipefail

DEST="${BOT_DIR:-$HOME/bot-tracker}"
PREFIX="${PREFIX:-/data/data/com.termux/files/usr}"
SHORTCUTS="$HOME/.shortcuts"
BOOT_HOOK="$HOME/.termux/boot/start-bot.sh"
PURGE=0
ASSUME_YES=0

while [ $# -gt 0 ]; do
    case "$1" in
        --purge) PURGE=1; shift ;;
        --yes|-y) ASSUME_YES=1; shift ;;
        -h|--help) sed -n '2,9p' "$0"; exit 0 ;;
        *) echo "Opción desconocida: $1" >&2; exit 2 ;;
    esac
done

if [ "$PURGE" -eq 1 ] && [ "$ASSUME_YES" -eq 0 ] && [ -r /dev/tty ]; then
    printf 'Se borrará %s (con backup de .env y tracker.db). ¿Seguir? [s/N] ' \
        "$DEST" > /dev/tty
    read -r answer < /dev/tty || answer=""
    case "$answer" in
        s|S|si|sí|y|Y) ;;
        *) echo "Cancelado."; exit 0 ;;
    esac
fi

echo "== Desinstalando el servicio =="
sv down bot 2>/dev/null || true
rm -rf "$PREFIX/var/service/bot"
rm -f "$BOOT_HOOK"
termux-wake-unlock 2>/dev/null || true

for shortcut in "Instalar bot" "Actualizar bot" "Estado" "Reiniciar bot" \
                "Ver logs" "Backup"; do
    rm -f "$SHORTCUTS/$shortcut"
done

tmux kill-session -t bot 2>/dev/null || true
pkill -f '[.]venv/bin/python main.py' 2>/dev/null || true

echo "✅ Servicio, arranque automático y atajos eliminados."

if [ "$PURGE" -eq 1 ]; then
    BACKUP_DIR="$HOME/bot-tracker-backups/uninstall-$(date +%Y%m%d-%H%M%S)"
    mkdir -p "$BACKUP_DIR"
    [ -f "$DEST/.env" ] && cp "$DEST/.env" "$BACKUP_DIR/env"
    [ -f "$DEST/tracker.db" ] && cp "$DEST/tracker.db" "$BACKUP_DIR/tracker.db"
    rm -rf "$DEST"
    echo "🗑 Proyecto eliminado. Copia de .env y tracker.db en:"
    echo "   $BACKUP_DIR"
else
    echo "Los datos siguen en $DEST (usa --purge para borrarlos)."
fi
