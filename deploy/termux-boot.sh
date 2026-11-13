#!/data/data/com.termux/files/usr/bin/sh
# Arranque automático del bot con Termux:Boot.
# Colócalo en ~/.termux/boot/start-bot.sh y dale permisos de ejecución.

termux-wake-lock

cd "$HOME/bot-tracker" || exit 1

if tmux has-session -t bot 2>/dev/null; then
    exit 0
fi

if pgrep -f '(^|/)[.]venv/bin/python main[.]py$' >/dev/null 2>&1; then
    exit 0
fi

tmux new-session -d -s bot \
    "cd '$HOME/bot-tracker' && exec .venv/bin/python main.py >> bot.log 2>&1"
