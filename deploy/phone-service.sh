#!/data/data/com.termux/files/usr/bin/bash
# Instala el bot como servicio supervisado con runit y configura el arranque
# automático con Termux:Boot.
#
# Uso:
#   bash deploy/phone-service.sh            # instala y arranca
#   bash deploy/phone-service.sh start
#   bash deploy/phone-service.sh stop
#   bash deploy/phone-service.sh restart
#   bash deploy/phone-service.sh status
#   bash deploy/phone-service.sh remove

set -euo pipefail

DEST="${BOT_DIR:-$HOME/bot-tracker}"
PREFIX="${PREFIX:-/data/data/com.termux/files/usr}"
SERVICE_NAME="bot"
SERVICE_DIR="$PREFIX/var/service/$SERVICE_NAME"
export SVDIR="$PREFIX/var/service"
LOG_DIR="$DEST/logs"
BOOT_HOOK="$HOME/.termux/boot/start-bot.sh"
ACTION="${1:-install}"

die() {
    echo "❌ $*" >&2
    exit 1
}

ensure_termux() {
    [ -d "$PREFIX" ] || die "esto no parece Termux (falta \$PREFIX)"
    command -v sv >/dev/null 2>&1 \
        || die "falta runit. Ejecuta: pkg install -y termux-services"
}

ensure_runsvdir() {
    if ! pgrep -f "runsvdir -P $PREFIX/var/service" >/dev/null 2>&1; then
        nohup "$PREFIX/bin/runsvdir" -P "$PREFIX/var/service" \
            >/dev/null 2>&1 &
        sleep 1
    fi
}

wait_for_service() {
    # runsvdir descubre los servicios nuevos cada pocos segundos.
    for _ in $(seq 1 10); do
        if sv status "$SERVICE_NAME" >/dev/null 2>&1; then
            return 0
        fi
        sleep 1
    done
    return 1
}

ensure_logs() {
    mkdir -p "$LOG_DIR"
    if [ ! -f "$LOG_DIR/config" ]; then
        printf 's5000000\nn3\n' > "$LOG_DIR/config"
    fi
}

install_service() {
    [ -x "$DEST/.venv/bin/python" ] \
        || die "falta $DEST/.venv. Ejecuta primero install.sh"

    ensure_logs
    mkdir -p "$SERVICE_DIR/log"

    cat > "$SERVICE_DIR/run" <<EOF
#!/data/data/com.termux/files/usr/bin/sh
exec 2>&1
cd "$DEST" || exit 1
exec .venv/bin/python main.py
EOF

    cat > "$SERVICE_DIR/log/run" <<EOF
#!/data/data/com.termux/files/usr/bin/sh
exec svlogd -tt "$LOG_DIR"
EOF

    # Rotación propia de svlogd: 5 MB por fichero, 3 ficheros.
    printf 's5000000\nn3\n' > "$LOG_DIR/config"

    chmod +x "$SERVICE_DIR/run" "$SERVICE_DIR/log/run"

    write_boot_hook
    ensure_runsvdir
    wait_for_service || true
    sv up "$SERVICE_NAME/log" 2>/dev/null || true
    sv up "$SERVICE_NAME" 2>/dev/null || true
    echo "✅ Servicio '$SERVICE_NAME' instalado en $SERVICE_DIR"
}

write_boot_hook() {
    mkdir -p "$(dirname "$BOOT_HOOK")"
    cat > "$BOOT_HOOK" <<EOF
#!/data/data/com.termux/files/usr/bin/sh
# Arranque automático del bot (Termux:Boot). Generado por phone-service.sh.
HOME=/data/data/com.termux/files/home
PREFIX=/data/data/com.termux/files/usr
export HOME PREFIX
export SVDIR="\$PREFIX/var/service"
export PATH="\$PREFIX/bin:\$PATH"

termux-wake-lock 2>/dev/null || true

if ! pgrep -f "runsvdir -P \$PREFIX/var/service" >/dev/null 2>&1; then
    nohup "\$PREFIX/bin/runsvdir" -P "\$PREFIX/var/service" >/dev/null 2>&1 &
    sleep 2
fi

"\$PREFIX/bin/sv" up $SERVICE_NAME/log 2>/dev/null || true
"\$PREFIX/bin/sv" up $SERVICE_NAME 2>/dev/null || true
sleep 3

# Respaldo: si runit no lo arrancó, usa tmux para no quedarte sin bot.
if ! "\$PREFIX/bin/sv" status $SERVICE_NAME 2>/dev/null | grep -q '^run:'; then
    if ! pgrep -f '[.]venv/bin/python main.py' >/dev/null 2>&1; then
        "\$PREFIX/bin/tmux" new-session -d -s $SERVICE_NAME \\
            "cd $DEST && exec .venv/bin/python main.py >> bot.log 2>&1"
    fi
fi
EOF
    chmod +x "$BOOT_HOOK"
    echo "✅ Arranque automático: $BOOT_HOOK"
}

service_status() {
    if sv status "$SERVICE_NAME" 2>/dev/null | grep -q '^run:'; then
        echo "✅ Servicio '$SERVICE_NAME' en ejecución"
        if sv status "$SERVICE_NAME/log" 2>/dev/null | grep -q '^run:'; then
            echo "✅ Servicio de logs en ejecución"
        else
            echo "⚠️ Servicio de logs detenido"
            return 1
        fi
        return 0
    fi
    echo "⚠️ Servicio '$SERVICE_NAME' detenido"
    sv status "$SERVICE_NAME" 2>/dev/null || true
    return 1
}

case "$ACTION" in
    install)
        ensure_termux
        install_service
        ;;
    start)
        ensure_termux
        ensure_logs
        write_boot_hook >/dev/null
        ensure_runsvdir
        wait_for_service || true
        sv up "$SERVICE_NAME/log" 2>/dev/null || true
        sv up "$SERVICE_NAME"
        ;;
    stop)
        ensure_termux
        sv down "$SERVICE_NAME" 2>/dev/null || true
        sv down "$SERVICE_NAME/log" 2>/dev/null || true
        echo "Servicio detenido."
        ;;
    restart)
        ensure_termux
        ensure_logs
        sv restart "$SERVICE_NAME/log" 2>/dev/null || true
        sv restart "$SERVICE_NAME" 2>/dev/null || sv up "$SERVICE_NAME"
        ;;
    status)
        ensure_termux
        service_status
        ;;
    remove)
        ensure_termux
        sv down "$SERVICE_NAME" 2>/dev/null || true
        sv down "$SERVICE_NAME/log" 2>/dev/null || true
        rm -rf "$SERVICE_DIR"
        rm -f "$BOOT_HOOK"
        echo "🗑 Servicio y arranque automático eliminados (datos conservados)."
        ;;
    *)
        die "acción desconocida: $ACTION"
        ;;
esac
