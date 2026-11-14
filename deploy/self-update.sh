#!/data/data/com.termux/files/usr/bin/bash
# Actualiza el bot desde Telegram. Lo lanza /actualizar en un proceso
# independiente para sobrevivir al reinicio del servicio.
#
# Uso (interno):
#   bash deploy/self-update.sh <chat_id>

set -uo pipefail

# Se re-ejecuta desde una copia temporal para que el git checkout de
# update.sh no modifique el script mientras bash lo está leyendo.
if [ -z "${BOT_TRACKER_SELF_UPDATE_REEXEC:-}" ]; then
    TMP_SCRIPT="$(mktemp)"
    cp "$0" "$TMP_SCRIPT"
    chmod +x "$TMP_SCRIPT"
    export BOT_TRACKER_SELF_UPDATE_REEXEC=1
    export BOT_TRACKER_SELF_UPDATE_TMP="$TMP_SCRIPT"
    exec bash "$TMP_SCRIPT" "$@"
fi

TMP_SCRIPT="${BOT_TRACKER_SELF_UPDATE_TMP:-}"
DEST="${BOT_DIR:-$HOME/bot-tracker}"
CHAT_ID="${1:-}"
PREFIX="${PREFIX:-/data/data/com.termux/files/usr}"
export SVDIR="$PREFIX/var/service"
export PATH="$PREFIX/bin:/system/bin:$PATH"

STATUS="$DEST/update-status"
LOG="$DEST/update.log"
LOCK="$DEST/.update-lock"

cleanup() {
    rmdir "$LOCK" 2>/dev/null || true
    [ -n "$TMP_SCRIPT" ] && rm -f "$TMP_SCRIPT" 2>/dev/null || true
}
trap cleanup EXIT

notify() {
    text="$1"
    printf '%s\n' "$text" >> "$LOG" 2>/dev/null || true
    [ -n "$CHAT_ID" ] || return 0
    [ -f "$DEST/.env" ] || return 0
    token="$(sed -n 's/^TELEGRAM_BOT_TOKEN=//p' "$DEST/.env" | head -n 1)"
    [ -n "$token" ] || return 0
    curl -fsS --max-time 15 \
        "https://api.telegram.org/bot${token}/sendMessage" \
        --data-urlencode "chat_id=${CHAT_ID}" \
        --data-urlencode "text=${text}" \
        >> "$LOG" 2>&1 || true
}

if ! mkdir "$LOCK" 2>/dev/null; then
    notify "⏳ Ya hay una actualización en curso."
    exit 1
fi

printf 'updating %s\n' "$(date -Iseconds 2>/dev/null || date)" > "$STATUS"
notify "🔄 Actualizando el bot… No lo apagues."

# Deja que Telegram entregue el mensaje anterior antes de parar el bot.
sleep 3

if ! cd "$DEST"; then
    printf 'failed\n' > "$STATUS"
    notify "❌ No encuentro $DEST."
    exit 1
fi

if bash "$DEST/update.sh"; then
    RESULT="ok"
else
    RESULT="failed"
fi

# Espera a que runit vuelva a levantar el servicio.
RUNNING=0
for _ in $(seq 1 30); do
    if sv status bot 2>/dev/null | grep -q '^run:'; then
        RUNNING=1
        break
    fi
    if pgrep -f '[.]venv/bin/python main.py' >/dev/null 2>&1; then
        RUNNING=1
        break
    fi
    sleep 2
done

NEW_VERSION="$(
    sed -n 's/^__version__ = "\(.*\)"/\1/p' "$DEST/version.py" 2>/dev/null \
        | head -n 1
)"

if [ "$RESULT" = "ok" ] && [ "$RUNNING" -eq 1 ]; then
    printf 'ok v%s\n' "$NEW_VERSION" > "$STATUS"
    notify "✅ Bot actualizado a v${NEW_VERSION} y en marcha."
else
    printf 'failed v%s\n' "$NEW_VERSION" > "$STATUS"
    notify "❌ La actualización falló. Revisa ~/bot-tracker/update.log."
    exit 1
fi
