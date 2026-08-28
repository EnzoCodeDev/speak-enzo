#!/usr/bin/env bash
# Arranca el backend de Enzo Speak (crea el venv la primera vez).
set -e
cd "$(dirname "$0")"

if [ ! -x ".venv/bin/python3" ] || ! ./.venv/bin/python3 -c 'import sys' >/dev/null 2>&1; then
  if [ -d ".venv" ]; then
    echo "🔧 El entorno virtual tiene rutas antiguas; reconstruyéndolo..."
    rm -rf -- .venv
  else
    echo "🔧 Creando entorno virtual..."
  fi
  python3 -m venv .venv
  ./.venv/bin/pip install -r requirements.txt
fi

echo "🚀 Enzo Speak backend en http://0.0.0.0:8100  (docs: /docs)"
exec ./.venv/bin/python3 -m uvicorn app.main:app --host 0.0.0.0 --port 8100 "$@"
