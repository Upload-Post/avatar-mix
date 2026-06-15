#!/usr/bin/env bash
# Atajo determinista del pipeline avatar-mix (pasos 3-6).
# Requiere que ya existan: work/<slug>/script.json y work/<slug>/clips/avatar_<id>.mp4
#
# Uso: bash scripts/run.sh <slug> [ruta_musica] [bg_mode] [aspect]
#   bg_mode = card (default) | hyperframes
#   aspect  = 16:9 (default) | 9:16 | both   (both genera las dos versiones)
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SLUG="${1:?Uso: run.sh <slug> [musica] [card|hyperframes] [16:9|9:16|both]}"
MUSIC="${2:-}"
BGMODE="${3:-card}"
ASPECT="${4:-16:9}"
WORK="$ROOT/work/$SLUG"

[ -f "$WORK/script.json" ] || { echo "Falta $WORK/script.json"; exit 1; }

echo "▸ 1/3  Midiendo duraciones de los clips de avatar…"
python3 - "$WORK" <<'PY'
import json, os, subprocess, sys
work = sys.argv[1]
sp = os.path.join(work, "script.json")
data = json.load(open(sp))
for sc in data["scenes"]:
    clip = os.path.join(work, "clips", f"avatar_{sc['id']}.mp4")
    if not os.path.exists(clip):
        sys.exit(f"Falta {clip}")
    d = float(subprocess.run(
        ["ffprobe","-v","error","-show_entries","format=duration",
         "-of","default=nk=1:nw=1", clip], capture_output=True, text=True).stdout.strip())
    sc["duration"] = round(d, 3)
    print(f"   escena {sc['id']} [{sc['mode']}] = {d:.2f}s")
json.dump(data, open(sp, "w"), ensure_ascii=False, indent=2)
PY

build() {
  local asp="$1"
  echo "▸ 2/3  Fondos ($BGMODE, $asp)…"
  python3 "$ROOT/scripts/make_bg.py" --slug "$SLUG" --mode "$BGMODE" --aspect "$asp"
  echo "▸ 3/3  Montaje ($asp)…"
  local args=(--slug "$SLUG" --aspect "$asp")
  [ -n "$MUSIC" ] && args+=(--music "$MUSIC")
  [ -f "$ROOT/assets/sfx/whoosh.mp3" ] && args+=(--whoosh "$ROOT/assets/sfx/whoosh.mp3")
  [ -f "$WORK/sfx_manifest.json" ] && args+=(--sfx-manifest "$WORK/sfx_manifest.json")
  python3 "$ROOT/scripts/composite.py" "${args[@]}"
}

if [ "$ASPECT" = "both" ]; then
  build "16:9"
  build "9:16"
else
  build "$ASPECT"
fi
