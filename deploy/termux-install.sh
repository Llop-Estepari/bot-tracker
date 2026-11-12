#!/data/data/com.termux/files/usr/bin/bash
# Instalador del bot en Termux.
#
# Antes de ejecutarlo, en Termux:
#   termux-setup-storage
#   bash ~/storage/downloads/bot-tracker/deploy/termux-install.sh
#
# El proyecto y el archivo .env.termux deben estar en
# ~/storage/downloads/bot-tracker (se copian por adb desde el portátil).

set -euo pipefail

SRC="$(cd "$(dirname "$0")/.." && pwd)"
DEST="$HOME/bot-tracker"
LOG="$SRC/install.log"

exec > >(tee "$LOG") 2>&1

echo "== Bot tracker: instalación en Termux =="
date
echo "origen: $SRC"
echo "destino: $DEST"

echo
echo "== 1/7 Instalando paquetes =="
pkg update -y
pkg install -y python tmux

echo
echo "== 2/7 Copiando proyecto =="
rm -rf "$DEST"
mkdir -p "$DEST"
tar -C "$SRC" \
    --exclude=.venv \
    --exclude=__pycache__ \
    --exclude='*.pyc' \
    --exclude=install.log \
    -cf - . | tar -C "$DEST" -xf -

echo
echo "== 3/7 Creando entorno virtual =="
cd "$DEST"
python -m venv .venv
.venv/bin/pip install --upgrade pip
.venv/bin/pip install -r requirements.txt

echo
echo "== 4/7 Configuración =="
if [ -f "$SRC/.env.termux" ]; then
    cp "$SRC/.env.termux" "$DEST/.env"
    chmod 600 "$DEST/.env"
    rm -f "$SRC/.env.termux"
else
    echo "AVISO: no existe .env.termux; revisa $DEST/.env"
fi

echo
echo "== 5/7 Base de datos e intervalo =="
if [ -f "$SRC/tracker.db" ]; then
    cp "$SRC/tracker.db" "$DEST/tracker.db"
    rm -f "$SRC/tracker.db"
else
    echo "AVISO: no existe tracker.db; se creará una base vacía."
fi
.venv/bin/python - <<'PY'
import sqlite3

connection = sqlite3.connect("tracker.db")
connection.execute(
    "UPDATE alerts SET interval_seconds = 300 WHERE interval_seconds < 300"
)
connection.commit()
rows = connection.execute(
    "SELECT id, name, active, interval_seconds FROM alerts ORDER BY id"
).fetchall()
print("búsquedas:", rows)
connection.close()
PY

echo
echo "== 6/7 Comprobando fuentes (Wallapop / Vinted) =="
.venv/bin/python scripts/check_sources.py || echo "CHECK_FUENTES_CON_FALLOS"

echo
echo "== 7/7 Arranque automático =="
mkdir -p "$HOME/.termux/boot"
cp "$DEST/deploy/termux-boot.sh" "$HOME/.termux/boot/start-bot.sh"
chmod +x "$HOME/.termux/boot/start-bot.sh"
termux-wake-lock || true

echo
echo "== INSTALACIÓN COMPLETA =="
echo "Arranca el bot con:"
echo
echo "  cd ~/bot-tracker && tmux new -s bot '.venv/bin/python main.py 2>&1 | tee -a bot.log'"
echo
echo "Log de instalación: $LOG"
