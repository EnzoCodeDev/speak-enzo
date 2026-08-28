# Enzo Speak — Backend (FastAPI)

## Correr en Ubuntu (servicio systemd) ⭐

```bash
./deploy/install.sh --user       # en tu PC: servicio de usuario, sin sudo
sudo ./deploy/install.sh         # en un servidor/VPS: servicio de sistema
./deploy/install.sh --user --port 9000   # puerto personalizado
./deploy/install.sh --user --uninstall   # quitar el servicio
```

El instalador crea el venv, instala dependencias, registra la unidad systemd
(`enzo-speak.service`), la arranca y comprueba `/api/health`. Comandos útiles:

```bash
systemctl --user status enzo-speak      # estado
systemctl --user restart enzo-speak     # reiniciar (tras actualizar código)
journalctl --user -u enzo-speak -f      # logs en vivo
sudo loginctl enable-linger $USER       # que siga vivo al cerrar sesión (modo --user)
sudo ufw allow 8100/tcp                 # si usas firewall ufw
```

(En modo sistema, quita `--user` de los comandos.)

## Correr con Docker

```bash
docker compose up -d      # construye la imagen y levanta en el puerto 8100
```

Los tokens persisten en `./data` (montado como volumen).

## Arrancar manual (desarrollo)

```bash
./run.sh                 # puerto 8100 por defecto
# o manualmente:
python3 -m venv .venv
./.venv/bin/pip install -r requirements.txt
./.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8100
```

Docs interactivas: `http://localhost:8100/docs`

## Endpoints

| Método | Ruta | Descripción |
|--------|------|-------------|
| GET | `/api/health` | Estado del servidor y proveedores configurados |
| GET/POST | `/api/settings` | Ver/guardar tokens de IA y proveedor activo |
| POST | `/api/call/chat` | Modo llamada: turno de conversación con corrección |
| POST | `/api/translate` | Traductor con alternativas, notas y ejemplos |
| POST | `/api/pronunciation/evaluate` | Evalúa pronunciación (multipart: `target_text` + `audio` o `transcript`) |
| GET | `/api/phrases` | Categorías de las 1000 frases esenciales |
| GET | `/api/phrases/{categoria}` | Frases de una categoría |
| GET | `/api/grammar/topics` | Temas de gramática |
| POST | `/api/grammar/exercise` | Genera mini-lección + 5 ejercicios con IA |
| POST | `/api/grammar/check` | Evalúa una respuesta abierta |
| GET | `/api/scenarios` | Lista de escenarios de rol |
| POST | `/api/scenarios/chat` | Turno del juego de rol |
| POST | `/api/scenarios/report` | Evaluación final del escenario |

## Proveedores de IA

- **Gemini** (`app/ai/gemini.py`): REST `generateContent`. Único que soporta
  **audio** → evaluación de acento real. Modelo por defecto: `gemini-2.5-flash`.
- **DeepSeek** (`app/ai/deepseek.py`): API compatible con OpenAI. Modelo: `deepseek-chat`.

Los tokens se guardan en `data/settings.json` (creado al primer guardado, no lo subas a git).
Todos los prompts pedagógicos viven en `app/prompts.py`.
