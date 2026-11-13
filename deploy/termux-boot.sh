#!/data/data/com.termux/files/usr/bin/sh
# Arranque automático del bot con Termux:Boot.
# Colócalo en ~/.termux/boot/start-bot.sh y dale permisos de ejecución.
#
# Prefiere el servicio runit; si no está disponible, usa tmux como respaldo.

HOME=/data/data/com.termux/files/home
PREFIX=/data/data/com.termux/files/usr
export HOME PREFIX
export SVDIR="$PREFIX/var/service"
export PATH="$PREFIX/bin:$PATH"

termux-wake-lock 2>/dev/null || true

if [ -x "$PREFIX/bin/runsvdir" ]; then
    if ! pgrep -f "runsvdir -P $PREFIX/var/service" >/dev/null 2>&1; then
        nohup "$PREFIX/bin/runsvdir" -P "$PREFIX/var/service" \
            >/dev/null 2>&1 &
        sleep 2
    fi
    "$PREFIX/bin/sv" up bot 2>/dev/null || true
    sleep 3
    if "$PREFIX/bin/sv" status bot 2>/dev/null | grep -q '^run:'; then
        exit 0
    fi
fi

cd "$HOME/bot-tracker" || exit 1

if tmux has-session -t bot 2>/dev/null; then
    exit 0
fi

if pgrep -f '(^|/)[.]venv/bin/python main[.]py$' >/dev/null 2>&1; then
    exit 0
fi

tmux new-session -d -s bot \
    "cd '$HOME/bot-tracker' && exec .venv/bin/python main.py >> bot.log 2>&1"
