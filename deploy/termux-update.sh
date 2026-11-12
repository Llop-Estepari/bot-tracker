#!/data/data/com.termux/files/usr/bin/bash
# Actualiza una instalación existente del bot en Termux.
#
# Uso:
#   bash ~/bot-tracker/deploy/termux-update.sh
#
# Hace backup de .env y tracker.db, actualiza el código por Git, valida que
# compila y reinicia el bot en tmux. Si algo falla después de parar el bot,
# vuelve al commit anterior y lo arranca de nuevo.
#
# No toca .env, .venv, tracker.db ni bot.log.

set -euo pipefail

# El script se re-ejecuta desde una copia temporal para que `git pull` no
# modifique el archivo mientras bash lo está leyendo.
if [ -z "${BOT_TRACKER_UPDATE_REEXEC:-}" ]; then
    SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
    tmp_script="$(mktemp)"
    cp "$0" "$tmp_script"
    chmod +x "$tmp_script"
    export BOT_TRACKER_UPDATE_REEXEC=1
    export BOT_TRACKER_DEST="$(cd "$SCRIPT_DIR/.." && pwd)"
    export BOT_TRACKER_TMP_SCRIPT="$tmp_script"
    exec bash "$tmp_script" "$@"
fi

if [ -n "${BOT_TRACKER_TMP_SCRIPT:-}" ]; then
    trap 'rm -f "$BOT_TRACKER_TMP_SCRIPT"' EXIT
fi

DEST="${BOT_TRACKER_DEST:-$HOME/bot-tracker}"
BACKUPS="$HOME/bot-tracker-backups"
SESSION="bot"

[ -d "$DEST" ] || {
    echo "❌ No existe el proyecto en $DEST" >&2
    exit 1
}
cd "$DEST"

mkdir -p "$BACKUPS"
exec > >(tee -a "$DEST/update.log") 2>&1

echo "== Bot tracker: actualización en Termux =="
date
echo "proyecto: $DEST"
echo

abort() {
    echo "❌ $*" >&2
    echo "No se ha modificado nada." >&2
    exit 1
}

[ -d .git ] || abort "esto no parece un clon de Git. Revisa el README (sección Termux)."
[ -x .venv/bin/python ] || abort "falta .venv. Ejecuta primero deploy/termux-install.sh."

if ! command -v pkg >/dev/null 2>&1; then
    abort "este script debe ejecutarse dentro de Termux."
fi
command -v git >/dev/null 2>&1 || pkg install -y git
command -v tmux >/dev/null 2>&1 || pkg install -y tmux

[ -z "$(git status --porcelain)" ] || abort \
    "hay cambios locales en el repo. Haz commit o descártalos antes de actualizar."

BEFORE="$(git rev-parse HEAD)"
STOPPED=0

stop_bot() {
    tmux kill-session -t "$SESSION" 2>/dev/null || true
}

start_bot() {
    if tmux has-session -t "$SESSION" 2>/dev/null; then
        return 0
    fi
    tmux new-session -d -s "$SESSION" \
        "cd '$DEST' && exec .venv/bin/python main.py >> bot.log 2>&1"
}

on_error() {
    local code=$?
    trap - ERR
    set +e
    echo
    echo "❌ La actualización ha fallado (código $code)." >&2
    if [ "$STOPPED" -eq 1 ]; then
        echo "↩️  Volviendo al commit $BEFORE" >&2
        git reset --hard "$BEFORE"
        start_bot
        echo "El bot se ha reiniciado con la versión anterior." >&2
        echo "Backups disponibles en: $BACKUPS" >&2
    fi
    exit "$code"
}

trap on_error ERR

echo "== 1/5 Parando el bot =="
stop_bot
STOPPED=1
echo "bot detenido"

echo
echo "== 2/5 Copia de seguridad =="
STAMP="$(date +%F-%H%M%S)"
if [ -f tracker.db ]; then
    cp tracker.db "$BACKUPS/tracker-$STAMP.db"
    echo "tracker.db -> $BACKUPS/tracker-$STAMP.db"
else
    echo "AVISO: no existe tracker.db; se creará una base nueva al arrancar."
fi
if [ -f .env ]; then
    cp .env "$BACKUPS/env-$STAMP"
    echo ".env       -> $BACKUPS/env-$STAMP"
else
    echo "AVISO: no existe .env."
fi

echo
echo "== 3/5 Actualizando código =="
git fetch --all --prune
git pull --ff-only
AFTER="$(git rev-parse HEAD)"
if [ "$BEFORE" = "$AFTER" ]; then
    echo "Ya estabas en la última versión ($AFTER)."
else
    echo "Actualizado: $BEFORE -> $AFTER"
fi

echo
echo "== 4/5 Dependencias y validación =="
if git diff --name-only "$BEFORE" "$AFTER" | grep -qE '(^|/)requirements.*\.txt$'; then
    echo "Cambiaron los requirements; instalando dependencias…"
    .venv/bin/pip install -r requirements-termux.txt
else
    echo "Sin cambios en dependencias."
fi

.venv/bin/python -m compileall -q \
    main.py config.py db.py filters.py geocode.py notifier.py \
    scheduler.py bot sources scripts

echo
echo "== 5/5 Arrancando el bot =="
start_bot
sleep 3
tmux has-session -t "$SESSION" 2>/dev/null || {
    echo "el bot no ha arrancado" >&2
    false
}
trap - ERR
STOPPED=0

echo
echo "✅ Actualización completada."
echo "Backups: $BACKUPS"
echo "Log del bot: $DEST/bot.log"
echo
tail -n 20 bot.log || true
