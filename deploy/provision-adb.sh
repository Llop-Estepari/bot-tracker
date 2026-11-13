#!/usr/bin/env bash
# Aprovisiona un móvil Android por USB: instala Termux y sus addons desde
# F-Droid, prepara el sistema para 24/7 y ejecuta el instalador del bot.
#
# Uso (desde el portátil, en la raíz del repo):
#   bash deploy/provision-adb.sh --token "123:ABC" --chat-id 123456789
#
# Opciones:
#   --token TOKEN       token de @BotFather (obligatorio salvo --env-file)
#   --chat-id IDS       chat_id(s) autorizados, separados por comas
#   --env-file RUTA     usa un .env ya preparado en vez de --token
#   --db RUTA           copia un tracker.db existente
#   --serial SERIAL     dispositivo ADB (si hay varios conectados)
#   --apk-dir RUTA      caché de APKs (por defecto ~/.cache/bot-tracker-apks)
#   --no-apks           no instala las apps de F-Droid
#   --no-remote         no ejecuta el instalador; solo deja todo listo
#   --remote-timeout N  segundos de espera de la instalación (por defecto 600)

set -euo pipefail

# Git Bash en Windows convierte /sdcard/... en rutas locales; se desactiva.
if [ -n "${MSYSTEM:-}" ]; then
    export MSYS_NO_PATHCONV=1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

TOKEN=""
CHAT_IDS=""
ENV_SRC=""
DB_SRC=""
SERIAL=""
APK_DIR="${HOME}/.cache/bot-tracker-apks"
INSTALL_APKS=1
RUN_REMOTE=1
REMOTE_TIMEOUT=600

die() { printf '\n❌ %s\n' "$*" >&2; exit 1; }
step() { printf '\n== %s ==\n' "$*"; }
ok() { printf '✅ %s\n' "$*"; }
warn() { printf '⚠️  %s\n' "$*"; }

usage() {
    sed -n '2,24p' "$0"
}

while [ $# -gt 0 ]; do
    case "$1" in
        --token) TOKEN="${2:-}"; shift 2 ;;
        --chat-id) CHAT_IDS="${2:-}"; shift 2 ;;
        --env-file) ENV_SRC="${2:-}"; shift 2 ;;
        --db) DB_SRC="${2:-}"; shift 2 ;;
        --serial) SERIAL="${2:-}"; shift 2 ;;
        --apk-dir) APK_DIR="${2:-}"; shift 2 ;;
        --no-apks) INSTALL_APKS=0; shift ;;
        --no-remote) RUN_REMOTE=0; shift ;;
        --remote-timeout) REMOTE_TIMEOUT="${2:-600}"; shift 2 ;;
        -h|--help) usage; exit 0 ;;
        *) die "opción desconocida: $1" ;;
    esac
done

# --------------------------- comprobaciones ------------------------------- #

step "1/8 Comprobando el ordenador"

if ! command -v adb >/dev/null 2>&1; then
    cat >&2 <<'EOF'
❌ Falta adb (Android Platform Tools).

Ubuntu/Debian:  sudo apt install -y android-tools-adb android-sdk-platform-tools-common
Fedora:         sudo dnf install -y android-tools
Arch:           sudo pacman -S --needed android-tools
macOS:          brew install android-platform-tools
Windows:        winget install --id Google.PlatformTools -e

En Windows usa Git Bash para ejecutar este script.
EOF
    exit 1
fi

command -v curl >/dev/null 2>&1 || die "falta curl"
[ -f "$REPO_ROOT/.env.example" ] \
    || die "ejecuta el script desde el repo del bot"

if [ -z "$TOKEN" ] && [ -z "$ENV_SRC" ]; then
    die "indica --token (o --env-file)"
fi
if [ -n "$TOKEN" ]; then
    case "$TOKEN" in
        *:*) ;;
        *) die "el token debe tener el formato 123456:ABC..." ;;
    esac
fi
if [ -n "$CHAT_IDS" ]; then
    case "$CHAT_IDS" in
        *[!0-9,]*|"") die "los chat_id deben ser números separados por comas" ;;
    esac
fi

ADB=(adb)
if [ -n "$SERIAL" ]; then
    ADB=(adb -s "$SERIAL")
fi

adb start-server >/dev/null 2>&1 || true
DEVICES="$("${ADB[@]}" devices | awk 'NR>1 && $2=="device" {print $1}')"
COUNT="$(printf '%s\n' "$DEVICES" | grep -c . || true)"
if [ "$COUNT" -eq 0 ]; then
    echo >&2
    "${ADB[@]}" devices >&2
    cat >&2 <<'EOF'
❌ No hay ningún móvil autorizado.

· Revisa el cable (debe ser de datos) y el puerto USB.
· Activa Opciones de desarrollador → Depuración USB.
· Acepta el aviso "¿Permitir depuración USB?" en el móvil.
· En Linux, instala android-sdk-platform-tools-common o las reglas udev.
EOF
    exit 1
fi

if [ "$COUNT" -gt 1 ] && [ -z "$SERIAL" ]; then
    printf '%s\n' "$DEVICES" >&2
    die "hay varios dispositivos; usa --serial"
fi

if [ -z "$SERIAL" ]; then
    SERIAL="$(printf '%s\n' "$DEVICES" | head -n 1)"
    ADB=(adb -s "$SERIAL")
fi

MODEL="$("${ADB[@]}" shell getprop ro.product.model 2>/dev/null | tr -d '\r')"
ANDROID="$("${ADB[@]}" shell getprop ro.build.version.release 2>/dev/null | tr -d '\r')"
ok "dispositivo: ${MODEL:-?} · Android ${ANDROID:-?} · $SERIAL"

# ------------------------------- APKs ------------------------------------- #

apk_url() {
    package="$1"
    code="$(curl -fsSL "https://f-droid.org/api/v1/packages/$package" \
        | sed -n 's/.*"suggestedVersionCode":\([0-9][0-9]*\).*/\1/p' \
        | head -n 1)"
    [ -n "$code" ] || return 1
    printf 'https://f-droid.org/repo/%s_%s.apk\n' "$package" "$code"
}

install_packages() {
    mkdir -p "$APK_DIR"
    for package in com.termux com.termux.boot com.termux.widget com.termux.api; do
        apk="$APK_DIR/$package.apk"
        if [ ! -s "$apk" ]; then
            url="$(apk_url "$package")" \
                || die "no se pudo resolver $package en F-Droid"
            echo "   descargando $package…"
            curl -fL --retry 3 --connect-timeout 20 -o "$apk" "$url" \
                || die "no se pudo descargar $url"
        fi
        if ! "${ADB[@]}" install -r -g "$apk" >/dev/null 2>&1; then
            warn "no se pudo instalar $package (¿'Instalar vía USB' desactivado?)"
        else
            ok "$package instalado"
        fi
    done
}

if [ "$INSTALL_APKS" -eq 1 ]; then
    step "2/8 Instalando Termux y addons desde F-Droid"
    install_packages
else
    step "2/8 Apps: omitidas (--no-apks)"
fi

# ----------------------------- sistema ------------------------------------ #

step "3/8 Preparando Android para 24/7"
"${ADB[@]}" shell pm grant com.termux android.permission.WRITE_EXTERNAL_STORAGE \
    >/dev/null 2>&1 || true
"${ADB[@]}" shell pm grant com.termux android.permission.READ_EXTERNAL_STORAGE \
    >/dev/null 2>&1 || true
"${ADB[@]}" shell cmd deviceidle whitelist +com.termux >/dev/null 2>&1 \
    && ok "Termux exento de la optimización de batería" \
    || warn "no se pudo eximir Termux de la optimización de batería"
"${ADB[@]}" shell device_config set_sync_disabled_for_tests persistent \
    >/dev/null 2>&1 || true
"${ADB[@]}" shell device_config put activity_manager max_phantom_processes \
    2147483647 >/dev/null 2>&1 \
    && ok "phantom process killer desactivado" \
    || warn "no se pudo desactivar el phantom process killer"
"${ADB[@]}" shell settings put global settings_enable_monitor_phantom_procs \
    false >/dev/null 2>&1 || true

# Termux:Boot necesita abrirse una vez para registrar el receptor de arranque.
"${ADB[@]}" shell monkey -p com.termux -c android.intent.category.LAUNCHER 1 \
    >/dev/null 2>&1 || true
sleep 2
"${ADB[@]}" shell monkey -p com.termux.boot 1 >/dev/null 2>&1 || true

# ---------------------------- Termux listo -------------------------------- #

step "4/8 Esperando a que Termux inicialice"
READY=0
for _ in $(seq 1 30); do
    if "${ADB[@]}" shell "run-as com.termux test -x files/usr/bin/pkg" \
        >/dev/null 2>&1; then
        READY=1
        break
    fi
    sleep 2
done
if [ "$READY" -eq 1 ]; then
    ok "Termux inicializado"
else
    warn "Termux aún no está listo; se intentará el arranque en primer plano"
fi

# ------------------------------ archivos ---------------------------------- #

step "5/8 Preparando configuración"
WORK="$(mktemp -d 2>/dev/null || mktemp -d -t bot-tracker)"
trap 'rm -rf "$WORK"' EXIT

ENV_FILE="$WORK/bot.env"
if [ -n "$ENV_SRC" ]; then
    [ -f "$ENV_SRC" ] || die "no existe $ENV_SRC"
    cp "$ENV_SRC" "$ENV_FILE"
else
    {
        printf 'TELEGRAM_BOT_TOKEN=%s\n' "$TOKEN"
        printf 'ALLOWED_CHAT_IDS=%s\n' "${CHAT_IDS:-}"
        sed -n '/^DATABASE_PATH=/,$p' "$REPO_ROOT/.env.example"
    } > "$ENV_FILE"
fi

"${ADB[@]}" push "$ENV_FILE" /sdcard/Download/bot.env >/dev/null
ok "configuración copiada (/sdcard/Download/bot.env)"

"${ADB[@]}" push "$SCRIPT_DIR/phone-install.sh" \
    /sdcard/Download/bot-install.sh >/dev/null
ok "instalador copiado (/sdcard/Download/bot-install.sh)"

if [ -n "$DB_SRC" ]; then
    [ -f "$DB_SRC" ] || die "no existe $DB_SRC"
    "${ADB[@]}" push "$DB_SRC" /sdcard/Download/bot-tracker.db >/dev/null
    ok "base de datos copiada (/sdcard/Download/bot-tracker.db)"
fi

"${ADB[@]}" shell rm -f /sdcard/Download/bot-install.done \
    >/dev/null 2>&1 || true

# ------------------------------ ejecución --------------------------------- #

step "6/8 Ejecutando el instalador en el móvil"
REMOTE_CMD='bash /sdcard/Download/bot-install.sh --yes --env-file /sdcard/Download/bot.env'
MODE=""

if [ "$RUN_REMOTE" -eq 0 ]; then
    MODE="manual"
elif "${ADB[@]}" shell "run-as com.termux true" >/dev/null 2>&1; then
    MODE="run-as"
    echo "   modo: ejecución directa (run-as)"
    "${ADB[@]}" shell \
        "run-as com.termux env HOME=/data/data/com.termux/files/home PREFIX=/data/data/com.termux/files/usr TMPDIR=/data/data/com.termux/files/usr/tmp PATH=/data/data/com.termux/files/usr/bin:/system/bin $REMOTE_CMD" \
        || warn "el instalador terminó con errores"
else
    MODE="fallback"
    echo "   modo: intento por RUN_COMMAND y, si no, comando en pantalla"
    "${ADB[@]}" shell am startservice --user 0 \
        -n com.termux/com.termux.app.RunCommandService \
        -a com.termux.RUN_COMMAND \
        --es com.termux.RUN_COMMAND_PATH \
        /data/data/com.termux/files/usr/bin/bash \
        --esa com.termux.RUN_COMMAND_ARGUMENTS \
        "/sdcard/Download/bot-install.sh,--yes,--env-file,/sdcard/Download/bot.env" \
        --ez com.termux.RUN_COMMAND_BACKGROUND false \
        >/dev/null 2>&1 || true
fi

# ------------------------------ verificación ------------------------------ #

step "7/8 Esperando el resultado"
DONE=0
ELAPSED=0
if [ "$RUN_REMOTE" -eq 1 ]; then
    while [ "$ELAPSED" -lt "$REMOTE_TIMEOUT" ]; do
        if "${ADB[@]}" shell test -f /sdcard/Download/bot-install.done \
            >/dev/null 2>&1; then
            DONE=1
            break
        fi
        if "${ADB[@]}" shell \
            "run-as com.termux test -f files/home/bot-install.done" \
            >/dev/null 2>&1; then
            DONE=1
            break
        fi
        sleep 3
        ELAPSED=$((ELAPSED + 3))
        if [ "$ELAPSED" -gt 0 ] && [ $((ELAPSED % 30)) -eq 0 ]; then
            echo "   … ${ELAPSED}s"
        fi
    done
fi

if [ "$DONE" -eq 1 ]; then
    ok "instalación terminada en el móvil"
    # El .env ya está en ~/bot-tracker: no dejamos el token en /sdcard.
    "${ADB[@]}" shell rm -f /sdcard/Download/bot.env >/dev/null 2>&1 || true
    if ! "${ADB[@]}" pull /sdcard/Download/bot-install.log \
        "$WORK/install.log" >/dev/null 2>&1; then
        "${ADB[@]}" shell \
            "run-as com.termux cat files/home/install.log" \
            > "$WORK/install.log" 2>/dev/null || true
    fi
    if [ -s "$WORK/install.log" ]; then
        echo
        echo "--- últimas líneas del instalador ---"
        tail -n 25 "$WORK/install.log"
    fi
else
    warn "no se pudo confirmar la instalación automáticamente"
fi

# ------------------------------- resumen ---------------------------------- #

step "8/8 Resumen"
cat <<EOF

En el móvil, comprueba:
  sv status bot
  bash ~/bot-tracker/deploy/phone-doctor.sh

En Telegram:
  /estado    → debe mostrar la versión instalada
  /nuevo     → crea tu primera búsqueda

Obligatorio en HyperOS/MIUI para 24/7:
  · Ajustes → Apps → Termux → Batería → Sin restricciones
  · Ajustes → Apps → Termux → Inicio automático → activado
  · Recientes → candado en Termux
EOF

if [ "$DONE" -ne 1 ]; then
    cat <<EOF

Si el bot no se ha instalado solo, abre Termux y pega:

  $REMOTE_CMD

Cuando termine, borra el token del almacenamiento compartido:

  rm -f /sdcard/Download/bot.env

EOF
    [ "$MODE" = "manual" ] && exit 0
    exit 4
fi

cat <<EOF

Todo listo. Para actualizar en el futuro, un toque en el widget
"Actualizar bot" o:

  bash ~/bot-tracker/update.sh
EOF
