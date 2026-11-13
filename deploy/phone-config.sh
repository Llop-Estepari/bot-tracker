#!/data/data/com.termux/files/usr/bin/bash
# Cambia el token o los chats autorizados del .env y reinicia el servicio.
#
# Uso:
#   bash deploy/phone-config.sh --token "123:ABC"
#   bash deploy/phone-config.sh --chat-id 123456789
#   bash deploy/phone-config.sh --chat-id 123456789 --restart
#   bash deploy/phone-config.sh --show

set -euo pipefail

DEST="${BOT_DIR:-$HOME/bot-tracker}"
PREFIX="${PREFIX:-/data/data/com.termux/files/usr}"
export SVDIR="$PREFIX/var/service"
ENV_FILE="$DEST/.env"
TOKEN=""
CHAT_IDS=""
RESTART=0
SHOW=0

die() {
    echo "❌ $*" >&2
    exit 1
}

while [ $# -gt 0 ]; do
    case "$1" in
        --token) TOKEN="${2:-}"; shift 2 ;;
        --chat-id) CHAT_IDS="${2:-}"; shift 2 ;;
        --restart) RESTART=1; shift ;;
        --show) SHOW=1; shift ;;
        -h|--help)
            sed -n '2,10p' "$0"
            exit 0
            ;;
        *) die "opción desconocida: $1" ;;
    esac
done

[ -d "$DEST" ] || die "no existe $DEST"
[ -f "$ENV_FILE" ] || die "no existe $ENV_FILE"

set_env() {
    key="$1"
    value="$2"
    if grep -q "^${key}=" "$ENV_FILE"; then
        sed -i "s|^${key}=.*|${key}=${value}|" "$ENV_FILE"
    else
        printf '%s=%s\n' "$key" "$value" >> "$ENV_FILE"
    fi
}

if [ "$SHOW" -eq 1 ]; then
    echo "Configuración actual ($ENV_FILE):"
    grep -E '^(TELEGRAM_BOT_TOKEN|ALLOWED_CHAT_IDS)=' "$ENV_FILE" \
        | sed -E 's|^(TELEGRAM_BOT_TOKEN=).*|\1***oculto***|'
    exit 0
fi

[ -n "$TOKEN$CHAT_IDS" ] \
    || die "indica --token y/o --chat-id (o usa --show)"

if [ -n "$TOKEN" ]; then
    case "$TOKEN" in
        *:*) ;;
        *) die "el token debe tener el formato 123456:ABC..." ;;
    esac
    set_env "TELEGRAM_BOT_TOKEN" "$TOKEN"
    echo "✅ Token actualizado"
fi

if [ -n "$CHAT_IDS" ]; then
    case "$CHAT_IDS" in
        *[!0-9,]*|"") die "los chat_id deben ser números separados por comas" ;;
    esac
    set_env "ALLOWED_CHAT_IDS" "$CHAT_IDS"
    echo "✅ Chats autorizados: $CHAT_IDS"
fi

chmod 600 "$ENV_FILE"

if [ "$RESTART" -eq 1 ]; then
    sv restart bot 2>/dev/null || sv up bot 2>/dev/null \
        || die "no se pudo reiniciar el servicio. ¿Está instalado runit?"
    sleep 2
    sv status bot 2>/dev/null || true
    echo "Comprueba /estado en Telegram."
fi
