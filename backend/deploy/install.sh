#!/usr/bin/env bash
# =============================================================================
# Enzo Speak — instalador para Ubuntu 💙
#
# Instala el backend como servicio systemd para que corra siempre y arranque
# solo al encender la máquina.
#
# Uso:
#   ./install.sh --user            # servicio de usuario (sin sudo, recomendado en tu PC)
#   sudo ./install.sh              # servicio de sistema (para un servidor/VPS)
#   ./install.sh --user --port 9000
#   ./install.sh --user --uninstall
# =============================================================================
set -euo pipefail

BACKEND_DIR="$(cd "$(dirname "$0")/.." && pwd)"
SERVICE_NAME="enzo-speak"
PORT=8100
MODE="system"
UNINSTALL=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --user) MODE="user"; shift ;;
    --port) PORT="$2"; shift 2 ;;
    --uninstall) UNINSTALL=1; shift ;;
    *) echo "Opción desconocida: $1"; exit 1 ;;
  esac
done

if [[ "$MODE" == "user" ]]; then
  UNIT_DIR="$HOME/.config/systemd/user"
  SYSTEMCTL=(systemctl --user)
  WANTED_BY="default.target"
else
  if [[ $EUID -ne 0 ]]; then
    echo "❌ El modo sistema necesita sudo. Usa: sudo $0   (o bien: $0 --user)"
    exit 1
  fi
  UNIT_DIR="/etc/systemd/system"
  SYSTEMCTL=(systemctl)
  WANTED_BY="multi-user.target"
fi

UNIT_FILE="$UNIT_DIR/$SERVICE_NAME.service"

if [[ $UNINSTALL -eq 1 ]]; then
  echo "🗑️  Desinstalando el servicio $SERVICE_NAME..."
  "${SYSTEMCTL[@]}" stop "$SERVICE_NAME" 2>/dev/null || true
  "${SYSTEMCTL[@]}" disable "$SERVICE_NAME" 2>/dev/null || true
  rm -f "$UNIT_FILE"
  "${SYSTEMCTL[@]}" daemon-reload
  echo "✅ Servicio eliminado. (El código y el venv siguen en $BACKEND_DIR)"
  exit 0
fi

echo "🔧 Preparando el entorno de Python en $BACKEND_DIR ..."
if [[ ! -d "$BACKEND_DIR/.venv" ]]; then
  python3 -m venv "$BACKEND_DIR/.venv"
fi
"$BACKEND_DIR/.venv/bin/pip" install -q --upgrade pip
"$BACKEND_DIR/.venv/bin/pip" install -q -r "$BACKEND_DIR/requirements.txt"

# En modo sistema, el servicio corre como el usuario que invocó sudo
# (los archivos viven en su home).
RUN_AS_LINES=""
if [[ "$MODE" == "system" && -n "${SUDO_USER:-}" ]]; then
  RUN_AS_LINES="User=$SUDO_USER"$'\n'"Group=$(id -gn "$SUDO_USER")"
fi

echo "📝 Escribiendo la unidad systemd en $UNIT_FILE ..."
mkdir -p "$UNIT_DIR"
cat > "$UNIT_FILE" <<EOF
[Unit]
Description=Enzo Speak — backend FastAPI (aprende inglés con IA)
After=network.target

[Service]
WorkingDirectory=$BACKEND_DIR
# Comillas obligatorias: la ruta puede contener espacios y systemd parte por espacios.
ExecStart="$BACKEND_DIR/.venv/bin/uvicorn" app.main:app --host 0.0.0.0 --port $PORT
Restart=always
RestartSec=3
$RUN_AS_LINES

[Install]
WantedBy=$WANTED_BY
EOF

"${SYSTEMCTL[@]}" daemon-reload
"${SYSTEMCTL[@]}" enable --now "$SERVICE_NAME"

echo "⏳ Esperando a que el servidor responda..."
for _ in $(seq 1 20); do
  if curl -fsS "http://localhost:$PORT/api/health" > /dev/null 2>&1; then
    break
  fi
  sleep 0.5
done

if curl -fsS "http://localhost:$PORT/api/health" > /dev/null 2>&1; then
  IP=$(hostname -I 2>/dev/null | awk '{print $1}')
  echo ""
  echo "🎉 ¡Enzo Speak backend corriendo como servicio!"
  echo "   · Salud:      http://localhost:$PORT/api/health"
  echo "   · Docs:       http://localhost:$PORT/docs"
  echo "   · Desde la app usa:  http://${IP:-TU_IP}:$PORT"
  echo ""
  echo "Comandos útiles:"
  echo "   ${SYSTEMCTL[*]} status $SERVICE_NAME     # estado"
  echo "   ${SYSTEMCTL[*]} restart $SERVICE_NAME    # reiniciar"
  if [[ "$MODE" == "user" ]]; then
    echo "   journalctl --user -u $SERVICE_NAME -f    # logs en vivo"
  else
    echo "   journalctl -u $SERVICE_NAME -f           # logs en vivo"
  fi
else
  echo "⚠️  El servicio se instaló pero aún no responde. Revisa los logs:"
  if [[ "$MODE" == "user" ]]; then
    echo "   journalctl --user -u $SERVICE_NAME -e"
  else
    echo "   journalctl -u $SERVICE_NAME -e"
  fi
  exit 1
fi

# Avisos finales -------------------------------------------------------------
if [[ "$MODE" == "user" ]]; then
  if ! loginctl show-user "$USER" 2>/dev/null | grep -q "Linger=yes"; then
    echo ""
    echo "💡 Para que el servicio siga corriendo aunque cierres sesión, ejecuta una vez:"
    echo "   sudo loginctl enable-linger $USER"
  fi
fi
if command -v ufw >/dev/null 2>&1 && ufw status 2>/dev/null | grep -q "Status: active"; then
  echo ""
  echo "💡 Tienes el firewall ufw activo. Abre el puerto para que tu teléfono llegue:"
  echo "   sudo ufw allow $PORT/tcp"
fi
