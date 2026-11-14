#!/data/data/com.termux/files/usr/bin/bash
# Crea los atajos de Termux:Widget para controlar el bot desde la pantalla
# de inicio: Actualizar bot y Estado.
#
# Uso:
#   bash deploy/phone-shortcuts.sh
#
# Después, instala Termux:Widget desde F-Droid y añade el widget.

set -euo pipefail

DEST="${BOT_DIR:-$HOME/bot-tracker}"
SHORTCUTS="$HOME/.shortcuts"

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

write_shortcut "Actualizar bot" \
    "exec bash \"$DEST/update.sh\""

write_shortcut "Estado" \
    "exec bash \"$DEST/deploy/phone-doctor.sh\""

# Limpia atajos de versiones anteriores.
for obsolete in "Backup" "Ver logs" "Instalar bot" "Reiniciar bot"; do
    rm -f "$SHORTCUTS/$obsolete"
done

echo
echo "✅ Atajos creados en $SHORTCUTS"
echo "Instala Termux:Widget desde F-Droid y añade el widget a la pantalla."
