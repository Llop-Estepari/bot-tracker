#!/data/data/com.termux/files/usr/bin/bash
# Actualiza una instalación existente del bot en Termux.
#
# Uso:
#   bash ~/bot-tracker/update.sh
#   bash ~/bot-tracker/deploy/termux-update.sh
#
# Hace backup de .env, tracker.db y del worktree, descarta los cambios locales
# (con backup), actualiza el código por Git, valida que compila, reinicia el
# bot (runit o tmux) y comprueba que arranca con la versión nueva. Si algo
# falla, vuelve al commit anterior y lo arranca de nuevo.
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
PREFIX="${PREFIX:-/data/data/com.termux/files/usr}"
SERVICE_DIR="$PREFIX/var/service/$SESSION"
export SVDIR="$PREFIX/var/service"
HAS_SERVICE=0
if command -v sv >/dev/null 2>&1 && [ -d "$SERVICE_DIR" ]; then
    HAS_SERVICE=1
fi

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
[ -x .venv/bin/python ] || abort "falta .venv. Ejecuta primero bash ~/bot-tracker/install.sh."

if ! command -v pkg >/dev/null 2>&1; then
    abort "este script debe ejecutarse dentro de Termux."
fi
command -v git >/dev/null 2>&1 || pkg install -y git
command -v tmux >/dev/null 2>&1 || pkg install -y tmux

BEFORE="$(git rev-parse HEAD)"
STOPPED=0
BOT_PROCESS_PATTERN='(^|/)[.]venv/bin/python main[.]py$'

# Evita dos actualizaciones simultáneas (widget + terminal + /actualizar).
UPDATE_LOCK="$DEST/.update-run-lock"
if ! mkdir "$UPDATE_LOCK" 2>/dev/null; then
    lock_pid="$(cat "$UPDATE_LOCK/pid" 2>/dev/null || true)"
    if [ -n "$lock_pid" ] && kill -0 "$lock_pid" 2>/dev/null; then
        echo "⏳ Ya hay una actualización en curso (pid $lock_pid)."
        echo "No se hace nada."
        exit 0
    fi
    echo "AVISO: lock de actualización obsoleto; se elimina." >&2
    rm -rf "$UPDATE_LOCK"
    mkdir "$UPDATE_LOCK" \
        || { echo "❌ No se pudo crear el lock de actualización." >&2; exit 1; }
fi
printf '%s\n' "$$" > "$UPDATE_LOCK/pid"
trap 'rm -rf "$UPDATE_LOCK"' EXIT

ensure_logs() {
    mkdir -p "$DEST/logs"
    if [ ! -f "$DEST/logs/config" ]; then
        printf 's5000000\nn3\n' > "$DEST/logs/config"
    fi
}

stop_bot() {
    # Con runit hay que bajar el servicio; si no, se relanza solo.
    if [ "$HAS_SERVICE" -eq 1 ]; then
        sv down "$SESSION" 2>/dev/null || true
        sv down "$SESSION/log" 2>/dev/null || true
        sleep 1
    fi
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
    ensure_logs
    if [ "$HAS_SERVICE" -eq 1 ]; then
        if ! pgrep -f "runsvdir -P $PREFIX/var/service" >/dev/null 2>&1; then
            nohup "$PREFIX/bin/runsvdir" -P "$PREFIX/var/service" \
                >/dev/null 2>&1 &
            sleep 1
        fi
        sv up "$SESSION/log" 2>/dev/null || true
        sv up "$SESSION" 2>/dev/null || true
        return 0
    fi
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
    if [ "$HAS_SERVICE" -eq 1 ]; then
        echo "--- estado del servicio ---" >&2
        sv status "$SESSION" 2>/dev/null >&2 || true
        tail -n 15 "$DEST/logs/current" 2>/dev/null >&2 || true
    fi
    if [ "$STOPPED" -eq 1 ]; then
        echo "↩️  Volviendo al commit $BEFORE" >&2
        stop_bot
        git reset --hard "$BEFORE"
        start_bot
        STOPPED=0
        echo "El bot se ha reiniciado con la versión anterior." >&2
        echo "Backups disponibles en: $BACKUPS" >&2
    fi
    exit "$code"
}

cleanup() {
    local code=$?
    trap - ERR
    if [ "${STOPPED:-0}" -eq 1 ]; then
        echo "↩️  El bot quedó parado; arrancándolo de nuevo…" >&2
        start_bot || true
        STOPPED=0
    fi
    rm -rf "$UPDATE_LOCK" 2>/dev/null || true
    if [ -n "${BOT_TRACKER_TMP_SCRIPT:-}" ]; then
        rm -f "$BOT_TRACKER_TMP_SCRIPT" 2>/dev/null || true
    fi
    return "$code"
}

trap on_error ERR
trap cleanup EXIT
trap 'exit 130' INT TERM

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
if [ "$HAS_SERVICE" -eq 1 ]; then
    LOG_FILE="$DEST/logs/current"
    LOG_LINES_BEFORE="$(wc -l < "$LOG_FILE" 2>/dev/null || echo 0)"
    start_bot
    for _ in $(seq 1 15); do
        if sv status "$SESSION" 2>/dev/null | grep -q '^run:'; then
            break
        fi
        sleep 1
    done
    sv status "$SESSION" 2>/dev/null | grep -q '^run:' || {
        echo "el servicio runit no está en ejecución" >&2
        false
    }
    if [ -d "$SERVICE_DIR/log" ] \
        && ! sv status "$SESSION/log" 2>/dev/null | grep -q '^run:'; then
        echo "el servicio de logs ($SESSION/log) no está en ejecución" >&2
        false
    fi
    if [ -n "$NEW_VERSION" ]; then
        for _ in $(seq 1 15); do
            if tail -n 500 "$LOG_FILE" 2>/dev/null \
                | grep -q "Arrancando el bot v${NEW_VERSION}"; then
                break
            fi
            sleep 1
        done
        if [ ! -f "$LOG_FILE" ]; then
            echo "no existe $LOG_FILE; revisa el servicio $SESSION/log" >&2
            false
        fi
        if ! tail -n 500 "$LOG_FILE" 2>/dev/null \
            | grep -q "Arrancando el bot v${NEW_VERSION}"; then
            echo "el bot no arrancó con la versión ${NEW_VERSION}" >&2
            false
        fi
    fi
else
    LOG_FILE="$DEST/bot.log"
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
fi
trap - ERR
STOPPED=0

# Regenera los atajos del widget (incluye actualizar, estado, logs…).
if [ -x deploy/phone-shortcuts.sh ] || [ -f deploy/phone-shortcuts.sh ]; then
    bash deploy/phone-shortcuts.sh >/dev/null 2>&1 || true
else
    mkdir -p "$HOME/.shortcuts" 2>/dev/null || true
    {
        printf '%s\n' '#!/data/data/com.termux/files/usr/bin/bash'
        printf '%s\n' 'exec bash "$HOME/bot-tracker/update.sh"'
    } > "$HOME/.shortcuts/Actualizar bot" 2>/dev/null || true
    chmod +x "$HOME/.shortcuts/Actualizar bot" 2>/dev/null || true
fi

echo
echo "✅ Actualización completada."
echo "Versión: ${NEW_VERSION:-desconocida}"
echo "Backups: $BACKUPS"
echo "Log del bot: $LOG_FILE"
echo
echo "Servicio:"
if [ "$HAS_SERVICE" -eq 1 ]; then
    sv status "$SESSION" 2>/dev/null | sed 's/^/  /' || true
else
    pgrep -af "$BOT_PROCESS_PATTERN" 2>/dev/null | sed 's/^/  /' || true
fi
if [ -n "$NEW_VERSION" ] && [ -f "$LOG_FILE" ]; then
    STARTUP_LINE="$(grep "Arrancando el bot v${NEW_VERSION}" \
        "$LOG_FILE" 2>/dev/null | tail -n 1 || true)"
    if [ -n "$STARTUP_LINE" ]; then
        echo "Arranque:"
        echo "  $STARTUP_LINE"
    fi
    NEW_LOG="$(tail -n +"$((LOG_LINES_BEFORE + 1))" "$LOG_FILE" 2>/dev/null || true)"
    if printf '%s' "$NEW_LOG" \
        | grep -Eq "ConnectError|No address associated|Error de red"; then
        echo
        echo "ℹ️  Hay avisos de red en el log; el bot los reintenta solo."
    fi
fi
