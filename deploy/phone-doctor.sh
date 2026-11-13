#!/data/data/com.termux/files/usr/bin/bash
# Diagnóstico del bot en Termux: servicio, proceso, arranque, batería y logs.
#
# Uso:
#   bash deploy/phone-doctor.sh
#
# Devuelve 1 si el servicio o el proceso no están sanos.

set -uo pipefail

DEST="${BOT_DIR:-$HOME/bot-tracker}"
PREFIX="${PREFIX:-/data/data/com.termux/files/usr}"
export SVDIR="$PREFIX/var/service"
WARNINGS=0
ERRORS=0

ok() { echo "✅ $*"; }
warn() { echo "⚠️  $*"; WARNINGS=$((WARNINGS + 1)); }
bad() { echo "❌ $*"; ERRORS=$((ERRORS + 1)); }

section() { printf '\n== %s ==\n' "$*"; }

section "Sistema"
if [ -d "$PREFIX" ] && command -v pkg >/dev/null 2>&1; then
    ok "Termux detectado ($PREFIX)"
else
    bad "no parece Termux"
fi

if [ -d "$DEST" ]; then
    ok "proyecto en $DEST"
else
    bad "no existe $DEST"
fi

section "Versión"
if [ -f "$DEST/version.py" ]; then
    VERSION="$(cd "$DEST" && .venv/bin/python -c \
        'import version; print(version.__version__, version.__release_date__)' \
        2>/dev/null || true)"
    if [ -n "$VERSION" ]; then
        ok "versión instalada: v$VERSION"
    else
        warn "no se pudo leer version.py con el venv"
    fi
else
    bad "falta version.py"
fi

section "Servicio (runit)"
if ! command -v sv >/dev/null 2>&1; then
    bad "falta runit (pkg install -y termux-services)"
elif sv status bot 2>/dev/null | grep -q '^run:'; then
    ok "servicio 'bot' en ejecución"
    sv status bot 2>/dev/null | sed 's/^/   /'
else
    bad "servicio 'bot' detenido"
    sv status bot 2>/dev/null | sed 's/^/   /'
fi

section "Proceso"
COUNT="$(pgrep -fc '[.]venv/bin/python main.py' 2>/dev/null || echo 0)"
if [ "$COUNT" -eq 1 ]; then
    ok "un único proceso main.py"
elif [ "$COUNT" -eq 0 ]; then
    bad "no hay ningún proceso main.py"
else
    warn "$COUNT procesos main.py (debería haber uno)"
    pgrep -af '[.]venv/bin/python main.py' | sed 's/^/   /'
fi

section "Arranque automático"
if [ -x "$HOME/.termux/boot/start-bot.sh" ]; then
    ok "hook de Termux:Boot presente"
else
    bad "falta ~/.termux/boot/start-bot.sh"
fi

PM="/system/bin/pm"
if [ -x "$PM" ] && "$PM" list packages 2>/dev/null | grep -q 'package:com.termux.boot'; then
    ok "Termux:Boot instalado"
else
    warn "Termux:Boot no detectado (instálalo desde F-Droid)"
fi

section "Batería y segundo plano"
SDK="$(getprop ro.build.version.sdk 2>/dev/null || echo 0)"
echo "   Android SDK: $SDK"
if [ "${SDK:-0}" -ge 31 ]; then
    warn "Android 12+: el sistema puede matar procesos en segundo plano"
    echo "   Lo importante es la batería sin restricciones (abajo)."
    echo "   Opcional con un PC por USB (una vez):"
    echo "   adb shell device_config put activity_manager max_phantom_processes 2147483647"
    echo "   adb shell settings put global settings_enable_monitor_phantom_procs false"
fi
echo "   Revisa a mano en HyperOS/MIUI:"
echo "   · Ajustes → Apps → Termux → Batería → Sin restricciones"
echo "   · Ajustes → Apps → Termux → Inicio automático → activado"
echo "   · Recientes → candado en Termux"

if command -v termux-battery-status >/dev/null 2>&1; then
    BATTERY="$(termux-battery-status 2>/dev/null | tr -d '\n' || true)"
    if [ -n "$BATTERY" ]; then
        echo "   Batería: $BATTERY"
    fi
fi

section "Red"
if curl -fsS -m 10 -o /dev/null https://api.telegram.org 2>/dev/null; then
    ok "Telegram accesible"
else
    warn "no se pudo comprobar Telegram (¿Wi-Fi?)"
fi

section "Logs"
if [ -f "$DEST/logs/current" ]; then
    ok "log de runit: $DEST/logs/current"
    echo "   tamaño: $(du -h "$DEST/logs/current" | cut -f1)"
    tail -n 5 "$DEST/logs/current" | sed 's/^/   /'
elif [ -f "$DEST/bot.log" ]; then
    ok "log clásico: $DEST/bot.log"
    tail -n 5 "$DEST/bot.log" | sed 's/^/   /'
else
    warn "sin logs todavía"
fi

section "Disco"
df -h "$HOME" 2>/dev/null | tail -n 1 | sed 's/^/   /'

section "Resumen"
if [ "$ERRORS" -gt 0 ]; then
    echo "❌ $ERRORS error(es), $WARNINGS aviso(s)."
    exit 1
fi
echo "✅ Sin errores, $WARNINGS aviso(s)."
