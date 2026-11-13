#!/data/data/com.termux/files/usr/bin/bash
# Actualiza una instalación existente del bot en Termux.
#
# Uso:
#   bash ~/bot-tracker/update.sh
#   bash ~/bot-tracker/deploy/termux-update.sh
#
# Hace backup de .env, tracker.db y del worktree, descarta los cambios locales
# (con backup), actualiza el código por Git, valida que compila, reinicia el
# bot en tmux y comprueba que arranca con la versión nueva. Si algo falla,
# vuelve al commit anterior y lo arranca de nuevo.
#
# Ejecútalo desde la shell normal de Termux, no desde dentro de
# `tmux attach -t bot`.
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

project_version() {
    sed -n 's/^__version__ = "\(.*\)"/\1/p' version.py 2>/dev/null | head -1
}

CURRENT_VERSION="$(project_version)"

echo "== Bot tracker: actualización en Termux =="
date
echo "proyecto: $DEST"
echo "versión actual: ${CURRENT_VERSION:-desconocida}"
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

BEFORE="$(git rev-parse HEAD)"
STOPPED=0
BOT_PROCESS_PATTERN='(^|/)[.]venv/bin/python main[.]py$'

stop_bot() {
    tmux kill-session -t "$SESSION" 2>/dev/null || true
    pkill -f "$BOT_PROCESS_PATTERN" 2>/dev/null || true
    sleep 1
    if pgrep -f "$BOT_PROCESS_PATTERN" >/dev/null 2>&1; then
        echo "AVISO: el bot sigue vivo; forzando parada" >&2
        pkill -9 -f "$BOT_PROCESS_PATTERN" 2>/dev/null || true
        sleep 1
    fi
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
        stop_bot
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

DIRTY="$(git status --porcelain)"
if [ -n "$DIRTY" ]; then
    echo
    echo "==> Cambios locales detectados (se descartarán):"
    echo "$DIRTY"
    git diff > "$BACKUPS/worktree-$STAMP.patch"
    printf '%s\n' "$DIRTY" > "$BACKUPS/worktree-$STAMP.status"
    tar -czf "$BACKUPS/worktree-$STAMP.tar.gz" \
        -C "$DEST" \
        --exclude=.git \
        --exclude=.venv \
        --exclude=.env \
        --exclude=tracker.db \
        --exclude='*.db' \
        --exclude='*.db-*' \
        --exclude='*.log' \
        --exclude=__pycache__ \
        --exclude=.pytest_cache \
        --exclude=.ruff_cache \
        .
    echo "Backup del worktree: $BACKUPS/worktree-$STAMP.tar.gz"
    echo "Diff:                $BACKUPS/worktree-$STAMP.patch"
else
    echo "Sin cambios locales."
fi

echo
echo "== 3/5 Actualizando código =="
echo "rama actual: $(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo desconocida)"
if [ -n "$DIRTY" ]; then
    echo "Descartando cambios locales (backup en $BACKUPS)…"
    git reset --hard HEAD
    git clean -fd
fi
git fetch --all --prune
# Garantiza la rama main y el commit exacto de origin/main, aunque la copia
# local esté en master, en detached HEAD o sin upstream configurado.
git checkout -B main origin/main
git branch --set-upstream-to=origin/main main >/dev/null 2>&1 || true
echo "rama tras actualizar: $(git rev-parse --abbrev-ref HEAD)"
AFTER="$(git rev-parse HEAD)"
NEW_VERSION="$(project_version)"
if [ "$BEFORE" = "$AFTER" ]; then
    echo "Ya estabas en la última versión ($AFTER)."
else
    echo "Actualizado: $BEFORE -> $AFTER"
fi
echo "versión tras el pull: ${NEW_VERSION:-desconocida}"

echo
echo "== 4/5 Dependencias y validación =="
if git diff --name-only "$BEFORE" "$AFTER" | grep -qE '(^|/)requirements.*\.txt$'; then
    echo "Cambiaron los requirements; instalando dependencias…"
    .venv/bin/pip install -r requirements.txt
else
    echo "Sin cambios en dependencias."
fi

.venv/bin/python -m compileall -q \
    main.py config.py db.py filters.py geo.py notifier.py \
    scheduler.py bot sources scripts

echo
echo "== 5/5 Arrancando el bot =="
LOG_LINES_BEFORE="$(wc -l < bot.log 2>/dev/null || echo 0)"
start_bot
sleep 3
tmux has-session -t "$SESSION" 2>/dev/null || {
    echo "el bot no ha arrancado (sesión tmux ausente)" >&2
    false
}
if ! pgrep -f "$BOT_PROCESS_PATTERN" >/dev/null 2>&1; then
    echo "el proceso del bot no está corriendo" >&2
    false
fi
if [ -n "$NEW_VERSION" ] && ! tail -n +"$((LOG_LINES_BEFORE + 1))" bot.log 2>/dev/null | grep -q "Arrancando el bot v${NEW_VERSION}"; then
    echo "el bot no arrancó con la versión ${NEW_VERSION}" >&2
    false
fi
trap - ERR
STOPPED=0

# Prepara el atajo del widget de Termux (Termux:Widget).
mkdir -p "$HOME/.shortcuts" 2>/dev/null || true
{
    printf '%s\n' '#!/data/data/com.termux/files/usr/bin/bash'
    printf '%s\n' 'exec bash "$HOME/bot-tracker/update.sh"'
} > "$HOME/.shortcuts/Actualizar bot" 2>/dev/null || true
chmod +x "$HOME/.shortcuts/Actualizar bot" 2>/dev/null || true

echo
echo "✅ Actualización completada."
echo "Versión: ${NEW_VERSION:-desconocida}"
echo "Backups: $BACKUPS"
echo "Log del bot: $DEST/bot.log"
echo
tail -n 20 bot.log || true
