#!/data/data/com.termux/files/usr/bin/bash
# Instalador del bot en Termux. Idempotente: se puede ejecutar varias veces.
#
# Uso normal (con el repo público):
#   curl -fsSL https://raw.githubusercontent.com/Llop-Estepari/bot-tracker/main/deploy/phone-install.sh | bash
#
# Uso desde el repo ya clonado:
#   bash deploy/phone-install.sh --token "123:ABC" --chat-id 123456789
#
# Opciones:
#   --token TOKEN        token de @BotFather
#   --chat-id IDS        chat_id(s) autorizados, separados por comas
#   --env-file RUTA      importa un .env ya preparado (ej. /sdcard/Download/bot.env)
#   --db RUTA            importa un tracker.db existente
#   --repo URL           repositorio Git (por defecto el oficial)
#   --dir RUTA           destino (por defecto ~/bot-tracker)
#   --skip-update        no ejecuta pkg update
#   --no-start           instala sin arrancar el servicio
#   --yes                sin preguntas (para automatización)

set -euo pipefail

export DEBIAN_FRONTEND=noninteractive

REPO_URL="https://github.com/Llop-Estepari/bot-tracker.git"
DEST="${BOT_DIR:-$HOME/bot-tracker}"
TOKEN=""
CHAT_IDS=""
ENV_SRC=""
DB_SRC=""
SKIP_UPDATE=0
START=1
ASSUME_YES=0
LOG=""

while [ $# -gt 0 ]; do
    case "$1" in
        --token) TOKEN="${2:-}"; shift 2 ;;
        --chat-id) CHAT_IDS="${2:-}"; shift 2 ;;
        --env-file) ENV_SRC="${2:-}"; shift 2 ;;
        --db) DB_SRC="${2:-}"; shift 2 ;;
        --repo) REPO_URL="${2:-}"; shift 2 ;;
        --dir) DEST="${2:-}"; shift 2 ;;
        --skip-update) SKIP_UPDATE=1; shift ;;
        --no-start) START=0; shift ;;
        --yes|-y) ASSUME_YES=1; shift ;;
        --log) LOG="${2:-}"; shift 2 ;;
        -h|--help) sed -n '2,25p' "${BASH_SOURCE[0]:-$0}"; exit 0 ;;
        *) echo "Opción desconocida: $1" >&2; exit 2 ;;
    esac
done

# ----------------------------- utilidades --------------------------------- #

step() { printf '\n== %s ==\n' "$*"; }
info() { printf '%s\n' "$*"; }
warn() { printf '⚠️  %s\n' "$*"; }
fail() { printf '❌ %s\n' "$*" >&2; exit 1; }

pick_log() {
    if [ -n "$LOG" ]; then
        return
    fi
    for candidate in /sdcard/Download "$HOME/storage/downloads" "$HOME"; do
        if [ -d "$candidate" ] && [ -w "$candidate" ]; then
            LOG="$candidate/bot-install.log"
            return
        fi
    done
    LOG="$HOME/install.log"
}

mark_done() {
    stamp="$(date -Iseconds 2>/dev/null || date)"
    for target in /sdcard/Download/bot-install.done "$HOME/bot-install.done"; do
        printf 'version=%s\ndate=%s\n' "$1" "$stamp" > "$target" 2>/dev/null || true
    done
}

find_shared_file() {
    # $1 = nombre del fichero; busca en las rutas típicas de almacenamiento.
    for dir in /sdcard/Download "$HOME/storage/downloads" \
               "$HOME/storage/shared/Download"; do
        if [ -f "$dir/$1" ]; then
            printf '%s\n' "$dir/$1"
            return 0
        fi
    done
    return 1
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

ask() {
    # Pregunta por /dev/tty para funcionar también con `curl | bash`.
    prompt="$1"
    if [ "$ASSUME_YES" -eq 1 ] || [ ! -r /dev/tty ]; then
        return 0
    fi
    printf '%s' "$prompt" > /dev/tty
    read -r answer < /dev/tty || answer=""
    printf '%s' "$answer"
}

# ------------------------------ requisitos -------------------------------- #

[ -n "${PREFIX:-}" ] && [ -x "$PREFIX/bin/pkg" ] \
    || fail "este script debe ejecutarse dentro de Termux (F-Droid)"
export SVDIR="$PREFIX/var/service"
command -v bash >/dev/null 2>&1 || fail "falta bash"

pick_log
exec > >(tee -a "$LOG") 2>&1

echo "== Bot tracker: instalación en Termux =="
date
echo "destino:  $DEST"
echo "repo:     $REPO_URL"
echo "log:      $LOG"

step "1/8 Paquetes"
if [ "$SKIP_UPDATE" -eq 0 ]; then
    pkg update -y || warn "pkg update falló; se continúa con los paquetes actuales"
fi
pkg install -y python git tmux termux-services termux-api curl tar \
    || fail "no se pudieron instalar los paquetes"

step "2/8 Código"
if [ -d "$DEST/.git" ]; then
    if [ -n "$(git -C "$DEST" status --porcelain 2>/dev/null || true)" ]; then
        BACKUP_DIR="$HOME/bot-tracker-backups"
        mkdir -p "$BACKUP_DIR"
        STAMP="$(date +%Y%m%d-%H%M%S)"
        git -C "$DEST" diff > "$BACKUP_DIR/install-$STAMP.patch" 2>/dev/null || true
        warn "había cambios locales; guardados en $BACKUP_DIR/install-$STAMP.patch"
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
info "versión del código: $(sed -n 's/__version__ = "\(.*\)"/\1/p' version.py)"

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
    info "dependencias ya instaladas (sin cambios)"
fi

step "4/8 Configuración"
if [ -z "$ENV_SRC" ]; then
    if candidate="$(find_shared_file bot.env)"; then
        ENV_SRC="$candidate"
    fi
fi

if [ -n "$ENV_SRC" ] && [ -f "$ENV_SRC" ]; then
    cp "$ENV_SRC" .env
    chmod 600 .env
    info ".env importado desde $ENV_SRC"
    # No dejamos el token en el almacenamiento compartido.
    case "$ENV_SRC" in
        /sdcard/*) rm -f "$ENV_SRC" 2>/dev/null || true ;;
    esac
elif [ -f .env ]; then
    info ".env existente conservado"
else
    cp .env.example .env
    chmod 600 .env
    info "creado .env a partir de .env.example"
fi

if [ -n "$TOKEN" ]; then
    case "$TOKEN" in
        *:*) set_env "TELEGRAM_BOT_TOKEN" "$TOKEN" ;;
        *) warn "el token no tiene formato 123:ABC; no se aplicó" ;;
    esac
fi
if [ -n "$CHAT_IDS" ]; then
    set_env "ALLOWED_CHAT_IDS" "$CHAT_IDS"
fi

if [ "$ASSUME_YES" -eq 0 ] && [ -r /dev/tty ]; then
    if ! grep -Eq '^TELEGRAM_BOT_TOKEN=.+' .env; then
        token="$(ask 'Token de @BotFather (vacío para saltar): ')"
        if [ -n "$token" ]; then
            set_env "TELEGRAM_BOT_TOKEN" "$token"
        fi
    fi
    if ! grep -Eq '^ALLOWED_CHAT_IDS=.+' .env; then
        chat="$(ask 'Tu chat_id de Telegram (vacío para saltar): ')"
        if [ -n "$chat" ]; then
            set_env "ALLOWED_CHAT_IDS" "$chat"
        fi
    fi
fi

if ! grep -Eq '^TELEGRAM_BOT_TOKEN=.+' .env; then
    warn "falta el token. Edítalo con: nano $DEST/.env"
fi

step "5/8 Base de datos"
if [ -z "$DB_SRC" ]; then
    if candidate="$(find_shared_file bot-tracker.db)"; then
        DB_SRC="$candidate"
    fi
fi
if [ -f tracker.db ]; then
    info "tracker.db existente conservado"
elif [ -n "$DB_SRC" ] && [ -f "$DB_SRC" ]; then
    cp "$DB_SRC" tracker.db
    info "tracker.db importado desde $DB_SRC"
else
    info "sin base de datos: se creará una vacía al arrancar"
fi

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
    for _ in $(seq 1 15); do
        if sv status bot 2>/dev/null | grep -q '^run:'; then
            break
        fi
        sleep 1
    done
else
    info "arranque omitido (--no-start)"
fi

step "8/8 Verificación"
VERSION="$(.venv/bin/python -c 'import version; print(version.__version__)')"
HEALTHY=1
if [ "$START" -eq 1 ]; then
    if sv status bot 2>/dev/null | grep -q '^run:'; then
        info "✅ servicio runit activo"
    else
        warn "el servicio no está en estado 'run'"
        sv status bot 2>/dev/null || true
        HEALTHY=0
    fi
    if pgrep -f '[.]venv/bin/python main.py' >/dev/null 2>&1; then
        info "✅ proceso del bot activo"
    else
        warn "no hay proceso main.py"
        HEALTHY=0
    fi
    if [ -f logs/current ] && grep -q "Arrancando el bot v$VERSION" logs/current; then
        info "✅ arrancó con la versión v$VERSION"
    else
        warn "no se encontró el arranque de v$VERSION en logs/current"
        tail -n 20 logs/current 2>/dev/null || true
    fi
fi

mark_done "$VERSION"

echo
if [ "$HEALTHY" -eq 1 ]; then
    echo "✅ INSTALACIÓN COMPLETA · v$VERSION"
else
    echo "⚠️  Instalación terminada con avisos · v$VERSION"
fi
cat <<EOF

Servicio:   sv status bot
Diagnóstico: bash $DEST/deploy/phone-doctor.sh
Logs:       tail -n 50 $DEST/logs/current

En HyperOS/MIUI (obligatorio para 24/7):
  · Ajustes → Apps → Termux → Batería → Sin restricciones
  · Ajustes → Apps → Termux → Inicio automático → activado
  · Recientes → candado en Termux

Comprueba en Telegram: /estado (debe mostrar v$VERSION)
EOF

if [ "$HEALTHY" -eq 0 ]; then
    exit 1
fi
