# Speak Enzo 💙

Practica inglés conversando con tu IA local. **Sin cuentas, sin claves,
sin nube**: todo corre en tu máquina con [Ollama](https://ollama.com).

Incluye **🎮 Subtítulos VRChat** ([vrchat-subtitulos/](vrchat-subtitulos/)):
subtítulos en tiempo real (solo inglés) para VRChat en Linux, con hablantes
separados por voz, traducción al español y respuestas sugeridas. Todo lo que
escuchas se guarda por semana en `web/vrchat/` y el botón **🎮 VRChat** de la
web lo analiza (palabras más usadas) y crea sesiones de práctica en pares.
Se arranca con `./vrchat-subtitulos/vrchat-subtitulos` (se auto-instala).

## 🚀 Arrancar (un solo comando)

```bash
./start.sh
```

Eso es todo. El script instala lo que falte (Ollama y un modelo si no tienes),
arranca la IA, sirve la web en **http://localhost:8180** y abre el navegador.

> Usa **Google Chrome**: el micrófono (reconocimiento de voz) solo funciona ahí.

## 🎮 Qué hace

Una sola función, bien hecha: **conversación con Enzo, tu tutor de inglés**.

- 🎙️ Hablas por el micrófono (o escribes) y Enzo responde en inglés, con voz
  y con la traducción al español debajo.
- ✏️ Cada mensaje tuyo recibe corrección de gramática, una forma más natural
  de decirlo y un consejo de acento cuando hablaste por voz.
- 🌱🌿🌳 **Tres niveles** (principiante / intermedio / avanzado) cambiables
  arriba en cualquier momento: la IA adapta vocabulario y exigencia al vuelo.
- 🔒 **Modo estricto**: si cometes un error, Enzo te da la frase correcta y
  cómo pronunciarla (aproximación fonética en español)... y **no te deja
  seguir la conversación hasta que la digas bien** — cada intento te marca
  en verde/rojo palabra por palabra.
- 🎵 **Canciones**: busca por título y artista en un catálogo de letras normales
  o sincronizadas; Enzo traduce sus frases y te guía una por una. Este recorrido es
  siempre estricto: no hay botón para saltar y solo avanzas al pronunciar la
  frase actual correctamente. Las canciones importadas, sus URL, frases y
  traducciones quedan guardadas en `web/songs/index.json`.

## 📁 Estructura

```
enzo-speak/
├── start.sh   → ⭐ arranca todo
├── web/       → la app (una sola página, sin dependencias)
├── app/       → versión Flutter anterior (pausada)
└── backend/   → versión FastAPI anterior (pausada)
```

Hecho con 💙 para aprender inglés.
