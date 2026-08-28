# Subtítulos VRChat (Linux)

Subtítulos en tiempo real, **solo en inglés**, para las personas que hablan en
VRChat. Cada persona tiene sus subtítulos por separado, con su propio nombre y
color — las voces nunca se mezclan. Con tu IA local (Ollama) puede además
**traducir al español** (solo si tú lo activas) y **sugerirte respuestas en
inglés** al hacer clic sobre una conversación.

![Overlay de subtítulos de VRChat](../docs/capturas/overlay-vrchat.png)

*(La ventana real del overlay, renderizada con una conversación de ejemplo.)*

Todo corre **localmente en tu PC** (Whisper en tu GPU + Ollama): no se envía
audio ni texto a ningún servicio externo.

> ⚠️ **Solo Ubuntu/Linux** (con PipeWire). No funciona en Windows ni macOS.

## Un solo comando

```bash
vrchat-subtitulos
```

Ese único comando **instala todo lo que falte y ejecuta**: si no hay entorno
de Python lo crea, si faltan dependencias las instala, si faltan modelos los
descarga, y arranca. En una máquina nueva basta con copiar la carpeta del
proyecto y correr `./vrchat-subtitulos`.

## Cómo usarlo

1. Abre VRChat y lanza `vrchat-subtitulos` (el orden da igual: la app se
   engancha sola al audio de VRChat cuando lo detecta; también arranca
   Ollama solo si está apagado).
2. Aparece una ventana flotante de tamaño fijo abajo de la pantalla.
   Arrástrala desde el borde y recuerda su posición.
3. Cuando alguien hable en inglés, sale su subtítulo: **Speaker 1:** hello!
4. **Ponles nombre**: doble clic sobre su línea (o clic derecho → «Renombrar
   hablante»). La app recuerda cada voz, así que esa persona conserva su
   nombre en futuras sesiones.

### Traducción al español (selecciona como en el navegador)

Igual que seleccionar texto en el navegador: **deja el clic apretado, pasa el
ratón por las frases** (se resaltan en azul) **y al soltar se traducen solo
esas**, debajo en gris. Mantener el clic quieto sobre una sola frase también
la selecciona. Nada se traduce si tú no lo seleccionas.

(Si algún día quieres que se traduzca todo sin tocar nada: clic derecho →
«Traducir TODO automáticamente». Por defecto está apagado.)

### Teclas rápidas (funcionan DENTRO del juego)

Aunque VRChat tenga el foco, sin tocar la ventana:

- **Tecla 9** → traduce las últimas 5 frases de golpe.
- **Tecla 0** → respuesta sugerida en inglés a lo último que dijeron.

(Se cambian en `~/.config/vrchat-subtitulos/config.json`:
`hotkey_translate` / `hotkey_suggest`.)

### Respuesta sugerida en inglés

- **Un clic sobre la línea de una conversación** → la IA local lee las
  últimas frases y te propone UNA respuesta corta y natural en inglés,
  con su traducción entre paréntesis para que sepas qué dice.
- La sugerencia trae tres líneas:
  - **💬 La frase en inglés** (lo que dirías).
  - **(Su traducción)** para que sepas qué significa.
  - **🗣 Cómo pronunciarla, escrita en español** — la lees tal cual y suena
    a inglés: *How are you today?* → `jau ar yu tudéi`.
- Botones: **Copiar** (al portapapeles), **Al chatbox** (la escribe en el
  chatbox de VRChat vía OSC — requiere activar OSC en el juego: Action Menu
  → Options → OSC → Enabled), **Otra** (nueva sugerencia), **✕** (cerrar).
- También desde el menú: clic derecho → «Sugerir respuesta ahora».

### Menú (clic derecho)

- Traducir TODO automáticamente — interruptor (apagado por defecto).
- Sugerir respuesta ahora.
- Modelo IA — elige entre tus modelos de Ollama (autodetecta; por defecto
  usa el más pequeño, p. ej. `qwen3.5:2b`, que responde en ~0.3 s).
- Renombrar hablante / Letra más grande o pequeña / Olvidar todas las voces / Salir.

### Opciones de terminal

```bash
vrchat-subtitulos --model medium   # Whisper más preciso (tiny/base/small/medium/large-v3)
vrchat-subtitulos --debug          # imprime estado, subtítulos y sugerencias en la terminal
```

## Cómo funciona

1. **Captura** únicamente la *salida* de audio de VRChat vía PipeWire
   (`parec --monitor-stream`), nunca tu micrófono. Si VRChat no está sonando,
   captura la salida general y se cambia sola a VRChat cuando aparece.
2. **Detección de voz** (Silero VAD) corta el audio en frases. Solo se
   subtitulan las voces **cercanas/fuertes**: el murmullo lejano se ignora
   y no gasta CPU (ajustable con `min_volume` en config.json — sube a 0.02
   para ser más estricto, baja a 0.008 para oír más lejos).
3. **Huella de voz** (NeMo TitaNet): cada frase se compara con las voces
   conocidas para saber *quién* habla. Voz nueva → «Speaker N».
4. **Whisper** transcribe y detecta idioma: si no es inglés, se descarta.
   Elige solo dónde correr: GPU si está libre, o CPU si VRChat ya se comió
   la memoria de video (con el juego abierto: modelo `base` en CPU, ~1 s
   por frase).
5. **Ollama** (opcional): traduce al español y sugiere respuestas en inglés.

## Importante sobre los nombres

VRChat entrega todas las voces mezcladas en un solo canal y no expone qué
usuario habla. Por eso la app distingue a las personas **por su voz**: tú les
asignas el nombre una vez y las reconoce automáticamente después.

## Nota para modo VR

La ventana vive en tu escritorio. En **modo escritorio**, pon VRChat en
ventana sin bordes. Con **visor (HMD)**, usa un overlay de escritorio dentro
de VR (OVR Toolkit, o `wlx-overlay-s` en Linux) y ancla la ventana
«Subtítulos VRChat» dentro del juego.

## Conexión con Enzo Speak 🎮💙

Todas las conversaciones se guardan **literal, por semana**, en
`<repo>/web/vrchat/<año>-W<semana>.json`
(configurable con `transcript_dir` en `~/.config/vrchat-subtitulos/config.json`). En Enzo Speak, el botón **🎮 VRChat**
analiza esas frases (palabras y expresiones más usadas) y crea sesiones de
práctica en pares con la IA local: te dicen algo típico de VRChat y tú
contestas en voz alta.

## Archivos

- `vrchat-subtitulos` — ejecutable auto-instalable (también en `~/.local/bin`
  y en el menú de aplicaciones como «Subtítulos VRChat»).
- `app/` — código (captura, pipeline, hablantes, IA local, OSC, overlay).
- `models/` — modelos ONNX (se descargan solos si faltan).
- `~/.config/vrchat-subtitulos/` — configuración y voces aprendidas.
- El modelo Whisper se descarga solo la primera vez (`~/.cache/huggingface`).
  Sin GPU funciona en CPU automáticamente.
