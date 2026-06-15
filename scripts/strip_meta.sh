#!/usr/bin/env bash
# Limpia TODA la metadata de un MP4 (encoder, fecha, handler_name, brands) sin recodificar.
# Uso: bash scripts/strip_meta.sh <entrada.mp4> [salida.mp4]
set -euo pipefail
IN="${1:?Uso: strip_meta.sh <entrada.mp4> [salida.mp4]}"
OUT="${2:-${IN%.mp4}_clean.mp4}"
ffmpeg -y -i "$IN" \
  -map_metadata -1 -map_chapters -1 \
  -fflags +bitexact -flags:v +bitexact -flags:a +bitexact \
  -metadata:s:v handler_name= -metadata:s:a handler_name= \
  -c copy -movflags +faststart "$OUT" 2>/dev/null
echo "✓ $OUT"
