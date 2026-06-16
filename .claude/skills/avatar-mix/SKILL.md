---
name: avatar-mix
description: >-
  Crea un video 16:9 con tu avatar HeyGen (tu cara + tu voz) presentando contenido,
  con montaje dinamico que alterna entre avatar a pantalla completa, avatar en esquina
  sobre un fondo, y solo fondo, con transiciones, musica y SFX. Acepta una URL o un guion.
  Usa cuando el usuario quiera generar un video de avatar a partir de una web o un guion.
---

# avatar-mix

Pipeline para producir un video 16:9 (1920x1080) donde **el avatar HeyGen del usuario**
presenta contenido sobre fondos generados, con un montaje que va alternando 3 modos.

## Motores
- **HeyGen MCP** (`https://mcp.heygen.com/mcp/v1/`, OAuth) → avatar hablando + audio/SFX.
- **HyperFrames** (`npx hyperframes`) o **tarjetas PIL** → video de fondo.
- **FFmpeg** (`scripts/composite.py`) → montaje, chroma-key, transiciones, mezcla de audio.

## Identidad del avatar (config por usuario)
- Copia `config/avatar.example.json` a `config/avatar.json` y rellena `avatar_id` + `voice_id`
  (descúbrelos con `list_avatar_looks` / `list_voices` del MCP; `get_current_user` para la cuenta).
- `config/avatar.json` está en `.gitignore` (es personal). Engine por defecto: **Avatar V**.
- Plan HeyGen recomendado: **Creator** (600 créditos). El free no permite varias escenas ni TTS.

## Los 3 modos de escena
- `fullscreen` → avatar a pantalla completa (arranque siempre en este modo).
- `corner` → fondo a pantalla completa + avatar en recuadro PiP (webcam). **NO se borra el fondo**
  (borde + esquinas redondeadas). En **16:9** va abajo-derecha (`corner` en config, ~28%).
  En **9:16** va **centrado abajo y más grande** (`corner_9x16` en config: ~58%, `position: bottom-center`).
- `bg_only` → solo el fondo; la voz del avatar sigue como locucion.

## Flujo (orden estricto por dependencias)

### 0. Config (una vez)
- `config/avatar.json`: rellenar `avatar_id` y `voice_id`. Obtenerlos con las tools MCP
  `list_avatar_looks` y `list_voices` (o `get_current_user`).
- Verificar entorno: `ffmpeg -version`, `node -v` (>=22), MCP conectado (`get_current_user`).

### 1. Entrada → guion por escenas
- Si la fuente es **URL** → `WebFetch` para extraer el contenido. Si es **guion**, usarlo tal cual.
- Redactar el guion hablado y segmentarlo en escenas. Crear `work/<slug>/script.json`
  (ver `templates/script.example.json`). Reglas:
  - Escena 1 = `fullscreen`.
  - Alternar `corner` / `bg_only` / `fullscreen` segun el ritmo del contenido.
  - Cada escena: `id`, `mode`, `narration`, `bg_visual` (`headline`, `subline`/`bullets`, `style`),
    `transition` (`fade`|`slide`|`cut`), `transition_after_sec`.
  - `style` de `bg_visual`: `title_card` | `bullets` | `fullbleed` | `screenshot` (con `image`).

### 2. Avatar (HeyGen MCP) — un clip por escena
Para cada escena, igual en todos los modos (no se toca el fondo del avatar):
- `mcp__heygen__create_video_from_avatar` con `avatarId`, `voiceId`, `script` = narration,
  `aspectRatio: "16:9"`, `resolution: "1080p"` (usar `720p` en pruebas), y SIEMPRE
  `engine: {"type": "avatar_v"}` (mejor calidad; ver config). Devuelve `video_id` y `status: waiting`.
- Plan free: cuota mensual de avatar muy limitada (~3 videos) y SIN TTS. Para varias escenas
  hace falta plan **Creator** ($29/mes, 600 creditos). ~20 creditos por video de 1 min.
- Poll con `mcp__heygen__get_video` (o REST `GET /v1/video_status.get?video_id=...` con
  `X-Api-Key` del `.env`) hasta `completed`; coger `video_url`.
- Descargar a `work/<slug>/clips/avatar_<id>.mp4` (curl).
- En `bg_only` el clip se genera igual; en el montaje solo se usa su audio.

### 3. Medir duraciones → completar script.json
- Para cada clip: `ffprobe -v error -show_entries format=duration -of default=nk=1:nw=1 clip`.
- Escribir `duration` (segundos) en cada escena de `script.json`. **Obligatorio** antes del paso 4.

### 4. Fondos (uno por escena → `work/<slug>/<bgdir>/<id>.mp4`)
**REGLA DE ORO (directriz del usuario):** los fondos deben ser **gráficos animados PROPIOS,
explicativos y visuales**, NO capturas de la web casi nunca. Generar nosotros con HyperFrames
mock-ups y data-viz que EXPLIQUEN el producto. Usar `hyperframes capture <url>` solo de forma
**puntual** (1 escena como mucho) cuando una prueba real aporte; no como recurso por defecto.

Componentes custom que funcionan muy bien (autorízalos en `work/<slug>/hf/index.html`):
  - **Chat del agente**: burbujas usuario/agente que entran en secuencia, con checks (✓ Conciliada…),
    adjuntos (📎 factura.pdf) y chips de preguntas. Comunica "todo desde un chat".
  - **Tarjeta de datos / conciliación**: card con **número que cuenta** (GSAP onUpdate → fmtEur con
    miles "8.412,55 €"), filas (cobros/comisiones/reembolsos) y sello "Conciliado". Para cifras/dinero.
  - **Hub de integraciones**: pill central "tu-app · API + MCP" → chips Claude/Cursor/ChatGPT + nota.
  - **Title cards** (intro/outro) y **flujos** (icono→agente→hecho).
  - Estética de marca: bg #0b0f1a, accent #3ddc97, glows en deriva, entradas animadas, paneo/zoom suave.

Modo rápido sin gráficos ricos: `--mode card` (tarjetas PIL responsivas).

**Registro siempre al día:** en cada render de HyperFrames el skill **sincroniza las animaciones
nuevas** del registro (`scripts/sync_animations.py`, lo llama `make_bg.py` una vez por proyecto vía
marcador `.animations_synced`). Así las animaciones que vaya publicando HeyGen (p. ej. las 9 de
código: `code-typing`, `code-diff`, `code-highlight`, `code-morph`, `code-particle-assemble`…)
aparecen disponibles en `compositions/` sin tocar nada. Manual: `python3 scripts/sync_animations.py
--hf work/<slug>/hf` (o `--all` para todo el registro; `HF_NO_SYNC=1` lo desactiva). Úsalas vía
`data-composition-src="compositions/<nombre>.html"`. Ideal para vídeos **code/dev explainer**
(avatar en `corner` + animación de código de fondo).

Flujo HyperFrames (v0.6.98, requiere Chrome — validado):
  1. **Dos proyectos** por formato: `work/<slug>/hf/` (16:9, root 1920x1080) y
     `work/<slug>/hf_9x16/` (vertical, root 1080x1920). `make_bg.py` elige por `--aspect`.
     Scaffold: `npx hyperframes init hf` (copiar package/hyperframes/meta.json al hf_9x16).
  2. Autorizar `index.html` con los componentes custom: cada escena = elementos `class="clip"` +
     `data-start`(acumulado)/`data-duration`(real)/`data-track-index`; timeline maestra paused en
     `window.__timelines["main"]`; `data-duration` del root = total. Solo lógica determinista.
  3. `python3 scripts/make_bg.py --slug <slug> --mode hyperframes --aspect 16:9|9:16`
     (renderiza el proyecto y trocea `renders/` en `<bgdir>/<id>.mp4`).
Para máxima calidad se pueden instalar las skills oficiales (`npx skills add heygen-com/hyperframes`
→ `/hyperframes-read-first`).

### 5. Musica / SFX (HeyGen MCP) — CONTEXTUAL POR VIDEO
La gracia: elegir SFX que peguen con el contenido de CADA video, no siempre los mismos.
- Musica: `search_audio_sounds` (type=music) con `music_query` → `assets/music.*`.
- SFX base: whoosh de transicion → `assets/sfx/whoosh.mp3`.
- SFX contextuales: leer el guion y, por cada momento que lo pida, buscar el efecto adecuado en
  HeyGen (`type=sound_effects`) y descargarlo a `assets/sfx/`. Ej.: "riser" en la intro,
  "coins/cash register" al hablar de dinero/Stripe, "single chime/notification" cuando aparece un
  chat, "achievement" al completar algo (factura conciliada, 303 listo).
- Escribir el manifiesto `work/<slug>/sfx_manifest.json`:
  `[{ "scene": <id>, "offset": <seg desde inicio de la escena>, "file": "assets/sfx/x.mp3", "gain_db": -12 }]`
  (tambien admite `{"at": <seg en timeline final>}`).
- HeyGen es la fuente de SFX; no hay otro CLI para esto (HyperFrames `tts/beats` es voz/musica).

### 6. Montaje (FFmpeg)
- `python3 scripts/composite.py --slug <slug> --aspect 16:9|9:16 [--music ...] [--whoosh assets/sfx/whoosh.mp3] [--sfx-manifest work/<slug>/sfx_manifest.json]`
- Produce `output/<slug>{_9x16}.mp4`, con los 3 modos, transiciones (`xfade`/`acrossfade`),
  musica con ducking (`sidechaincompress`) y SFX (con `alimiter` final).
  **La salida YA sale sin metadata** (composite.py llama a `strip_meta` al final). Un solo archivo limpio.
- **Doble formato sin gastar avatar**: los mismos clips sirven para 16:9 y 9:16. Atajo:
  `bash scripts/run.sh <slug> <musica> <card|hyperframes> both` genera las dos versiones (ya limpias).

### 6.5 Subtítulos estilo Hormozi (recomendado para 9:16 — Reels/TikTok)
Palabras grandes en MAYÚSCULAS, palabra activa resaltada en acento, animadas. Flujo:
- Timing por palabra: `mcp__heygen__create_speech` (voz starfish) por escena devuelve `word_timestamps`
  → guardar en `work/<slug>/captions_src.json` (`[{id, tts_dur, words:[{t,start,end}]}]`).
  (Whisper local NO disponible: Anaconda tiene conflicto NumPy/Numba.)
- `python3 scripts/make_captions.py --slug <slug> --aspect 9:16` → genera `work/<slug>/hf_captions/`
  (proyecto HyperFrames transparente; escala cada escena a la duración real del clip y evita solapes).
- `python3 scripts/burn_captions.py --slug <slug> --aspect 9:16` → renderiza el MOV con alfa
  (ProRes 4444), hace el overlay, **deja la salida sin metadata** y borra el MOV. Produce
  `output/<slug>_9x16_subs.mp4` (un solo archivo limpio).
  - Detalles internos: MOV (no WebM; el VP9-alpha no overlaya bien con este FFmpeg). `capY` (~60% alto)
    coloca los subs por encima del avatar (bottom-center).

### 7. Entregar
- Mostrar la ruta de `output/<slug>.mp4` y un resumen de escenas/duracion.
- **Los MP4 de `output/` ya salen sin metadata** (encoder/fecha/handler) — no hay doble versión.
  `scripts/strip_meta.sh` queda disponible por si hay que limpiar un fichero externo.

### 8. Publicar en redes (Upload-Post API — subida directa del fichero local)
Sube los DOS formatos a todas las redes con `scripts/publish.sh` (API REST de Upload-Post via curl;
**sube el MP4 local directamente**, sin staging ni URL pública). Genérico: cada persona usa su
`UPLOAD_POST_API_KEY` (.env) y su propio perfil.
- Perfil: cada cuenta tiene uno o varios "user profiles" con sus redes conectadas. Listar con
  `curl -H "Authorization: Apikey $KEY" https://api.upload-post.com/api/uploadposts/users`.
- Vertical (con subs) → short-form:
  `bash scripts/publish.sh output/<slug>_9x16_subs.mp4 <perfil> tiktok,instagram,youtube,threads "<titulo>" "<desc>" "#hashtags" REELS`
- Horizontal → long-form:
  `bash scripts/publish.sh output/<slug>.mp4 <perfil> youtube,linkedin,facebook,x "<titulo>" "<desc>"`
- El script es asincrono (`request_id`) y hace poll a `/uploadposts/status`. Confirmar SIEMPRE antes.
- Regla: **vertical → TikTok/Reels/Shorts/Threads · horizontal → YouTube/LinkedIn/Facebook/X**.
- Alternativa: el MCP `Upload-Post` (tools `upload_video`/`get_status`), pero al ser remoto NO lee
  rutas locales (requiere `open_upload_studio` o URL publica) — por eso el script con la API es mejor aqui.

## Atajo determinista
Pasos 3-6 (cuando ya existen `clips/avatar_<id>.mp4`): `bash scripts/run.sh <slug> [musica]`.

## Estructura por proyecto (work/<slug>/)
- `script.json` (guion+duraciones), `clips/avatar_<id>.mp4` (HeyGen Avatar V),
- `hf/` (proyecto HyperFrames 16:9) y `hf_9x16/` (proyecto HyperFrames vertical),
- `hf/captured/` (solo si se usó `hyperframes capture` puntual),
- `bg/` y `bg_9x16/` (fondos troceados por escena), `sfx_manifest.json`.

## Notas
- `config/avatar.json`: marca, `corner` (PiP 16:9) y `corner_9x16` (PiP vertical: bottom-center, ~58%).
- Si `make_bg --mode card` no encuentra fuente TTF, instalar fuentes o usar `--mode hyperframes`.
- El FFmpeg de Homebrew de esta maquina **no trae `drawtext`** (sin libfreetype): las tarjetas PIL
  se renderizan con Pillow. Los gráficos ricos van por HyperFrames (Chrome headless).
