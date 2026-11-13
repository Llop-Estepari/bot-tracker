#!/data/data/com.termux/files/usr/bin/bash
# Crea los atajos de Termux:Widget para controlar el bot desde la pantalla
# de inicio.
#
# Uso:
#   bash deploy/phone-shortcuts.sh
#
# Después, instala Termux:Widget desde F-Droid y añade el widget.

set -euo pipefail

DEST="${BOT_DIR:-$HOME/bot-tracker}"
SHORTCUTS="$HOME/.shortcuts"
TERMUX_BIN="/data/data/com.termux/files/usr/bin"

die() {
    echo "❌ $*" >&2
    exit 1
}

[ -d "$DEST" ] || die "no existe $DEST"
mkdir -p "$SHORTCUTS"

write_shortcut() {
    name="$1"
    shift
    {
        printf '%s\n' "#!/data/data/com.termux/files/usr/bin/bash"
        printf '%s\n' "cd \"$DEST\" || exit 1"
        printf '%s\n' "PREFIX=/data/data/com.termux/files/usr"
        printf '%s\n' 'export SVDIR="$PREFIX/var/service"'
        printf '%s\n' "$@"
    } > "$SHORTCUTS/$name"
    chmod +x "$SHORTCUTS/$name"
    echo "· $name"
}

write_shortcut "Instalar bot" \
    "exec bash \"$DEST/install.sh\""

write_shortcut "Actualizar bot" \
    "exec bash \"$DEST/update.sh\""

write_shortcut "Estado" \
    "exec bash \"$DEST/deploy/phone-doctor.sh\""

write_shortcut "Reiniciar bot" \
    "\"$TERMUX_BIN/sv\" restart bot 2>/dev/null || \"$TERMUX_BIN/sv\" up bot" \
    "sleep 2" \
    "\"$TERMUX_BIN/sv\" status bot"

write_shortcut "Ver logs" \
    "tail -n 100 -f \"$DEST/logs/current\" 2>/dev/null || tail -n 100 -f \"$DEST/bot.log\""

write_shortcut "Backup" \
    "STAMP=\$(date +%F-%H%M)" \
    "DEST_DIR=/sdcard/Download" \
    "[ -d \"\$DEST_DIR\" ] || DEST_DIR=\"\$HOME\"" \
    "cp \"$DEST/tracker.db\" \"\$DEST_DIR/bot-tracker-\$STAMP.db\"" \
    "echo \"Copia de tracker.db guardada en \$DEST_DIR\""

echo
echo "✅ Atajos creados en $SHORTCUTS"
echo "Instala Termux:Widget desde F-Droid y añade el widget a la pantalla."
