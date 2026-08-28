#!/usr/bin/env bash
# ============================================================================
#  Speak Enzo 💙 — TODO con un solo comando:
#    ./start.sh
#  Instala lo que falte, arranca Ollama (tu IA local), sirve la web y
#  abre el navegador. Ctrl+C para parar.
# ============================================================================
set -e
cd "$(dirname "$0")"

PORT=8180
URL="http://localhost:$PORT"
OLLAMA_URL="http://localhost:11434"
MODEL_DEFAULT="qwen3.5:4b"

say() { printf '\033[1;35m💙 %s\033[0m\n' "$*"; }

# --------------------------------------------------------- 1. Ollama instalado
if ! command -v ollama >/dev/null 2>&1; then
  say "Ollama no está instalado. Instalándolo (puede pedir tu contraseña)..."
  curl -fsSL https://ollama.com/install.sh | sh
fi

# --------------------------------------------------------- 2. Ollama corriendo
if ! curl -s -m 2 "$OLLAMA_URL/api/tags" >/dev/null 2>&1; then
  say "Arrancando Ollama..."
  nohup ollama serve >/tmp/speak_enzo_ollama.log 2>&1 &
  for _ in $(seq 1 30); do
    curl -s -m 2 "$OLLAMA_URL/api/tags" >/dev/null 2>&1 && break
    sleep 1
  done
fi
if ! curl -s -m 2 "$OLLAMA_URL/api/tags" >/dev/null 2>&1; then
  say "❌ No pude arrancar Ollama. Mira /tmp/speak_enzo_ollama.log"
  exit 1
fi

# --------------------------------------------------- 3. Al menos un modelo IA
if ! curl -s "$OLLAMA_URL/api/tags" | grep -q '"name"'; then
  say "No tienes ningún modelo. Descargando $MODEL_DEFAULT (solo la primera vez)..."
  ollama pull "$MODEL_DEFAULT"
fi

# ------------------------------------------------- 4. python3 (sirve la app)
if ! command -v python3 >/dev/null 2>&1; then
  say "Instalando python3 (puede pedir tu contraseña)..."
  sudo apt-get update -y && sudo apt-get install -y python3
fi

# ---------------------------------------- 5. alias del overlay de VRChat
# Crea (una sola vez) el comando `vrchat-subs` para abrir los subtítulos
# desde cualquier terminal. El overlay usa el mismo Ollama local de arriba.
BASHRC="$HOME/.bashrc"
if [ -f "$BASHRC" ] && ! grep -q "alias vrchat-subs=" "$BASHRC"; then
  {
    echo ""
    echo "# Subtítulos VRChat (Speak Enzo)"
    echo "alias vrchat-subs='$(pwd)/vrchat-subtitulos/vrchat-subtitulos'"
  } >> "$BASHRC"
  say "Alias creado: escribe 'vrchat-subs' en una terminal NUEVA para abrir los subtítulos de VRChat"
fi

# --------------------------------------------------- 6. ¿ya estaba corriendo?
abrir() {
  if command -v google-chrome >/dev/null 2>&1; then
    nohup google-chrome "$URL" >/dev/null 2>&1 &
  elif command -v xdg-open >/dev/null 2>&1; then
    nohup xdg-open "$URL" >/dev/null 2>&1 &
  fi
}
if curl -s -m 2 "$URL/api/health" 2>/dev/null | grep -q '"songs": true'; then
  say "Speak Enzo ya estaba corriendo → $URL"
  abrir
  exit 0
fi

# Versiones anteriores usaban http.server. Si quedó una abierta, la reemplaza
# únicamente cuando coincide exactamente con el servidor viejo de este proyecto.
OLD_SERVER_PID=$(pgrep -f "^python3 -m http\.server $PORT --bind 127\.0\.0\.1 --directory web$" | head -1 || true)
if [ -n "$OLD_SERVER_PID" ]; then
  say "Actualizando el servidor anterior para activar Canciones..."
  kill "$OLD_SERVER_PID"
  for _ in $(seq 1 20); do
    kill -0 "$OLD_SERVER_PID" 2>/dev/null || break
    sleep 0.1
  done
elif curl -s -m 2 "$URL" >/dev/null 2>&1; then
  say "❌ El puerto $PORT está ocupado por otro programa. Ciérralo y ejecuta ./start.sh otra vez."
  exit 1
fi

# --------------------------------------------------------- 7. web + navegador
( sleep 1; abrir ) &
say "Speak Enzo listo → $URL   (usa Google Chrome para el micrófono · Ctrl+C para parar)"
exec python3 web/server.py --port "$PORT"
