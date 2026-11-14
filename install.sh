#!/data/data/com.termux/files/usr/bin/bash
# Instalador del bot en Termux, sin ordenador ni ADB.
#
# Uso (una sola línea, con Termux abierto):
#   bash <(curl -fsSL https://raw.githubusercontent.com/Llop-Estepari/bot-tracker/main/install.sh)
#
# También vale:
#   curl -fsSL https://raw.githubusercontent.com/Llop-Estepari/bot-tracker/main/install.sh | bash
#
# Opciones:
#   --token TOKEN     token de @BotFather (si no, lo pide)
#   --chat-id IDS     chat_id(s) autorizados, separados por comas
#   --db RUTA         restaura un tracker.db existente
#   --dir RUTA        destino (por defecto ~/bot-tracker)
#   --repo URL        repositorio Git
#   --skip-update     no ejecuta pkg update
#   --no-start        instala sin arrancar el servicio
#   --yes             sin preguntas (requiere --token o .env existente)

set -euo pipefail
export DEBIAN_FRONTEND=noninteractive

usage() {
    cat <<'EOF'
Instalador del bot en Termux (sin ordenador ni ADB).

Uso:
  bash <(curl -fsSL https://raw.githubusercontent.com/Llop-Estepari/bot-tracker/main/install.sh)

Opciones:
  --token TOKEN     token de @BotFather (si no, lo pide)
  --chat-id IDS     chat_id(s) autorizados, separados por comas
  --db RUTA         restaura un tracker.db existente
  --dir RUTA        destino (por defecto ~/bot-tracker)
  --repo URL        repositorio Git
  --skip-update     no ejecuta pkg update
  --no-start        instala sin arrancar el servicio
  --yes             sin preguntas (requiere --token o .env existente)
EOF
}

REPO_URL="https://github.com/Llop-Estepari/bot-tracker.git"
DEST="${BOT_DIR:-$HOME/bot-tracker}"
TOKEN=""
CHAT_IDS=""
DB_SRC=""
SKIP_UPDATE=0
START=1
ASSUME_YES=0
LOG="$HOME/bot-install.log"

while [ $# -gt 0 ]; do
    case "$1" in
        --token) TOKEN="${2:-}"; shift 2 ;;
        --chat-id) CHAT_IDS="${2:-}"; shift 2 ;;
        --db) DB_SRC="${2:-}"; shift 2 ;;
        --dir) DEST="${2:-}"; shift 2 ;;
        --repo) REPO_URL="${2:-}"; shift 2 ;;
        --skip-update) SKIP_UPDATE=1; shift ;;
        --no-start) START=0; shift ;;
        --yes|-y) ASSUME_YES=1; shift ;;
        --log) LOG="${2:-}"; shift 2 ;;
        -h|--help) usage; exit 0 ;;
        *) echo "Opción desconocida: $1" >&2; exit 2 ;;
    esac
done

step() { printf '\n== %s ==\n' "$*"; }
ok() { printf '✅ %s\n' "$*"; }
warn() { printf '⚠️  %s\n' "$*"; }
fail() { printf '❌ %s\n' "$*" >&2; exit 1; }

[ -n "${PREFIX:-}" ] && [ -x "$PREFIX/bin/pkg" ] \
    || fail "este instalador debe ejecutarse dentro de Termux (F-Droid)"
export SVDIR="$PREFIX/var/service"

# --------------------------- entrada de datos ----------------------------- #

tty_ok() { [ -r /dev/tty ] && [ -w /dev/tty ]; }

ask() {
    prompt="$1"
    default="${2:-}"
    if ! tty_ok; then
        printf '%s' "$default"
        return 0
    fi
    printf '%s' "$prompt" > /dev/tty
    IFS= read -r answer < /dev/tty || answer=""
    [ -z "$answer" ] && answer="$default"
    printf '%s' "$answer"
}

ask_secret() {
    prompt="$1"
    if ! tty_ok; then
        return 0
    fi
    printf '%s' "$prompt" > /dev/tty
    IFS= read -rs answer < /dev/tty || answer=""
    printf '\n' > /dev/tty
    printf '%s' "$answer"
}

set_env() {
    key="$1"
    value="$2"
    if grep -q "^${key}=" "$DEST/.env"; then
        sed -i "s|^${key}=.*|${key}=${value}|" "$DEST/.env"
    else
        printf '%s=%s\n' "$key" "$value" >> "$DEST/.env"
    fi
}

python_bin() {
    if [ -x "$DEST/.venv/bin/python" ]; then
        printf '%s' "$DEST/.venv/bin/python"
    else
        printf 'python'
    fi
}

# ------------------------------ preparación ------------------------------- #

exec > >(tee -a "$LOG") 2>&1

echo "== Bot tracker: instalación en Termux =="
date
echo "destino: $DEST"
echo "log:     $LOG"

step "1/8 Paquetes"
if [ "$SKIP_UPDATE" -eq 0 ]; then
    pkg update -y || warn "pkg update falló; se continúa con los paquetes actuales"
fi
pkg install -y python git curl tmux termux-services tar \
    || fail "no se pudieron instalar los paquetes base"

step "2/8 Código"
if [ -d "$DEST/.git" ]; then
    if [ -n "$(git -C "$DEST" status --porcelain 2>/dev/null || true)" ]; then
        mkdir -p "$HOME/bot-tracker-backups"
        STAMP="$(date +%Y%m%d-%H%M%S)"
        git -C "$DEST" diff > "$HOME/bot-tracker-backups/install-$STAMP.patch" \
            2>/dev/null || true
        warn "cambios locales guardados en ~/bot-tracker-backups/install-$STAMP.patch"
        git -C "$DEST" reset --hard HEAD
        git -C "$DEST" clean -fd
    fi
    git -C "$DEST" remote set-url origin "$REPO_URL"
    git -C "$DEST" fetch --all --prune
    git -C "$DEST" checkout -B main origin/main
    git -C "$DEST" branch --set-upstream-to=origin/main main >/dev/null 2>&1 || true
else
    mkdir -p "$(dirname "$DEST")"
    git clone --depth 1 "$REPO_URL" "$DEST"
fi
cd "$DEST"
ok "versión del código: $(sed -n 's/__version__ = "\(.*\)"/\1/p' version.py)"

step "3/8 Dependencias de Python"
if [ ! -x .venv/bin/python ]; then
    python -m venv .venv
fi
REQ_HASH="$(sha256sum requirements.txt | cut -d' ' -f1)"
if [ ! -f .venv/.requirements.sha256 ] \
    || [ "$(cat .venv/.requirements.sha256 2>/dev/null)" != "$REQ_HASH" ]; then
    .venv/bin/pip install --upgrade pip
    .venv/bin/pip install -r requirements.txt
    printf '%s\n' "$REQ_HASH" > .venv/.requirements.sha256
else
    ok "dependencias ya instaladas (sin cambios)"
fi

# ----------------------------- token y chats ------------------------------ #

step "4/8 Bot de Telegram"

validate_token() {
    response="$(curl -fsS "https://api.telegram.org/bot$1/getMe" 2>/dev/null)" \
        || return 1
    printf '%s' "$response" | "$(python_bin)" -c '
import json, sys
try:
    data = json.load(sys.stdin)
except Exception:
    sys.exit(1)
if not data.get("ok"):
    sys.exit(1)
print(data["result"]["username"])
' 2>/dev/null
}

detect_chat_id() {
    for attempt in $(seq 1 30); do
        updates="$(curl -fsS \
            "https://api.telegram.org/bot$1/getUpdates?timeout=0&allowed_updates=%5B%22message%22%5D" \
            2>/dev/null || true)"
        chat="$(printf '%s' "$updates" | "$(python_bin)" -c '
import json, sys
try:
    data = json.load(sys.stdin)
except Exception:
    sys.exit(0)
for update in reversed(data.get("result", [])):
    message = update.get("message") or {}
    chat = message.get("chat") or {}
    if chat.get("type") == "private" and chat.get("id"):
        print(chat["id"])
        break
' 2>/dev/null || true)"
        if [ -n "$chat" ]; then
            printf '%s' "$chat"
            return 0
        fi
        if [ $((attempt % 10)) -eq 0 ]; then
            echo "   … esperando $((attempt * 3))s"
        fi
        sleep 3
    done
    return 1
}

if [ -z "$TOKEN" ] && [ -f "$DEST/.env" ]; then
    TOKEN="$(sed -n 's/^TELEGRAM_BOT_TOKEN=//p' "$DEST/.env" | head -n 1)"
fi

for attempt in 1 2 3; do
    if [ -z "$TOKEN" ]; then
        [ "$ASSUME_YES" -eq 1 ] && fail "falta --token (o un .env existente)"
        TOKEN="$(ask_secret 'Pega el token de @BotFather (no se muestra): ')"
    fi
    [ -n "$TOKEN" ] || fail "sin token no se puede continuar"

    if BOT_USERNAME="$(validate_token "$TOKEN")" && [ -n "$BOT_USERNAME" ]; then
        ok "bot validado: @$BOT_USERNAME"
        break
    fi
    warn "el token no es válido (intento $attempt/3)"
    TOKEN=""
done
[ -n "${BOT_USERNAME:-}" ] || fail "no se pudo validar el token con Telegram"

if [ -z "$CHAT_IDS" ] && [ -f "$DEST/.env" ]; then
    CHAT_IDS="$(sed -n 's/^ALLOWED_CHAT_IDS=//p' "$DEST/.env" | head -n 1)"
fi

if [ -z "$CHAT_IDS" ] && [ "$ASSUME_YES" -eq 0 ]; then
    cat <<EOF

Abre este enlace en Telegram y pulsa START (o envía /start):
  https://t.me/$BOT_USERNAME

Buscaré tu chat_id automáticamente durante 90 segundos…
EOF
    CHAT_IDS="$(detect_chat_id "$TOKEN" || true)"
    if [ -n "$CHAT_IDS" ]; then
        ok "chat_id detectado: $CHAT_IDS"
    else
        warn "no detecté tu chat_id"
        CHAT_IDS="$(ask 'Escríbelo a mano (o Enter para saltar): ')"
    fi
fi

if [ -z "$CHAT_IDS" ]; then
    warn "sin chat autorizado: el bot te dirá tu chat_id al escribirle"
    warn "luego ejecuta: bash $DEST/deploy/phone-config.sh --chat-id TU_ID --restart"
fi

# ------------------------------ configuración ----------------------------- #

step "5/8 Configuración"
if [ ! -f .env ]; then
    cp .env.example .env
    chmod 600 .env
    ok "creado .env"
else
    ok ".env existente conservado"
fi

case "$TOKEN" in
    *:*) set_env "TELEGRAM_BOT_TOKEN" "$TOKEN" ;;
    *) fail "el token no tiene el formato 123456:ABC" ;;
esac
[ -n "$CHAT_IDS" ] && set_env "ALLOWED_CHAT_IDS" "$CHAT_IDS"
if [ -n "$CHAT_IDS" ] && ! grep -Eq '^ADMIN_CHAT_IDS=.+' .env; then
    set_env "ADMIN_CHAT_IDS" "$CHAT_IDS"
fi
chmod 600 .env

if [ -f tracker.db ]; then
    ok "tracker.db existente conservado"
elif [ -n "$DB_SRC" ] && [ -f "$DB_SRC" ]; then
    cp "$DB_SRC" tracker.db
    ok "tracker.db restaurado desde $DB_SRC"
else
    ok "sin base de datos: se creará vacía al arrancar"
fi

# -------------------------------- servicio -------------------------------- #

step "6/8 Servicio y arranque automático"
sv down bot 2>/dev/null || true
tmux kill-session -t bot 2>/dev/null || true
pkill -f '[.]venv/bin/python main.py' 2>/dev/null || true
sleep 1
bash "$DEST/deploy/phone-service.sh" install
bash "$DEST/deploy/phone-shortcuts.sh"
termux-wake-lock 2>/dev/null || warn "no se pudo activar el wake-lock"

step "7/8 Arranque"
if [ "$START" -eq 1 ]; then
    bash "$DEST/deploy/phone-service.sh" start
    for _ in $(seq 1 20); do
        if sv status bot 2>/dev/null | grep -q '^run:'; then
            break
        fi
        sleep 1
    done
else
    ok "arranque omitido (--no-start)"
fi

step "8/8 Verificación"
VERSION="$(.venv/bin/python -c 'import version; print(version.__version__)')"
HEALTHY=1
if [ "$START" -eq 1 ]; then
    if sv status bot 2>/dev/null | grep -q '^run:'; then
        ok "servicio runit activo"
    else
        warn "el servicio no está en estado 'run'"
        sv status bot 2>/dev/null || true
        HEALTHY=0
    fi
    if pgrep -f '[.]venv/bin/python main.py' >/dev/null 2>&1; then
        ok "proceso del bot activo"
    else
        warn "no hay proceso main.py"
        HEALTHY=0
    fi
    if [ -f logs/current ] && grep -q "Arrancando el bot v$VERSION" logs/current; then
        ok "arrancó con la versión v$VERSION"
    else
        warn "no se encontró el arranque de v$VERSION en logs/current"
        tail -n 20 logs/current 2>/dev/null || true
    fi
fi

echo
if [ "$HEALTHY" -eq 1 ]; then
    echo "✅ INSTALACIÓN COMPLETA · v$VERSION"
else
    echo "⚠️  Instalación terminada con avisos · v$VERSION"
fi

cat <<EOF

Tu bot:     https://t.me/$BOT_USERNAME
Servicio:   sv status bot
Diagnóstico: bash $DEST/deploy/phone-doctor.sh
Logs:       tail -n 50 $DEST/logs/current
Actualizar:  bash $DEST/update.sh

Para que funcione 24/7 en HyperOS/MIUI:
  · Ajustes → Apps → Termux → Batería → Sin restricciones
  · Ajustes → Apps → Termux → Inicio automático → activado
  · Recientes → candado en Termux

Abre Termux:Boot una vez (icono de la app) para registrar el arranque.
En Telegram: /estado debe mostrar v$VERSION.
EOF

if [ "$HEALTHY" -eq 0 ]; then
    exit 1
fi
