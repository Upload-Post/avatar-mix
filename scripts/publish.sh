#!/usr/bin/env bash
# Publica un video LOCAL en varias redes via la API de Upload-Post (subida directa, sin staging).
# Requiere UPLOAD_POST_API_KEY en .env. Consigue tu key en https://app.upload-post.com (Settings → API).
#
# Uso:
#   bash scripts/publish.sh <fichero.mp4> <perfil> <plataformas_csv> "<titulo>" ["descripcion"] ["#hashtags primer comentario"] [media_type]
#
# Ejemplos:
#   # vertical (Reels/Shorts/TikTok/Threads)
#   bash scripts/publish.sh output/demo_9x16_subs.mp4 mi_perfil tiktok,instagram,youtube,threads \
#        "Mi titulo" "Mi descripcion" "#hashtag1 #hashtag2" REELS
#   # horizontal (YouTube/LinkedIn/Facebook/X)
#   bash scripts/publish.sh output/demo.mp4 mi_perfil youtube,linkedin,facebook,x \
#        "Mi titulo" "Mi descripcion"
#
# Tip: lista tus perfiles con  curl -s -H "Authorization: Apikey $KEY" https://api.upload-post.com/api/uploadposts/users
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
[ -f "$ROOT/.env" ] && set -a && . "$ROOT/.env" && set +a
: "${UPLOAD_POST_API_KEY:?Falta UPLOAD_POST_API_KEY en .env}"

FILE="${1:?Falta el fichero de video}"
PROFILE="${2:?Falta el perfil (user)}"
PLATFORMS="${3:?Faltan plataformas (csv): tiktok,instagram,youtube,linkedin,facebook,x,threads,...}"
TITLE="${4:?Falta el titulo}"
DESC="${5:-}"
FIRST_COMMENT="${6:-}"
MEDIA_TYPE="${7:-}"          # p.ej. REELS para Instagram en vertical
BASE="${UPLOAD_POST_API_BASE:-https://api.upload-post.com/api}"

[ -f "$FILE" ] || { echo "No existe el fichero: $FILE"; exit 1; }

# construir flags -F platform[]=... por cada plataforma
ARGS=(-F "user=$PROFILE" -F "title=$TITLE" -F "video=@${FILE}" -F "async_upload=true")
[ -n "$DESC" ] && ARGS+=(-F "description=$DESC")
[ -n "$FIRST_COMMENT" ] && ARGS+=(-F "first_comment=$FIRST_COMMENT")
[ -n "$MEDIA_TYPE" ] && ARGS+=(-F "media_type=$MEDIA_TYPE")
IFS=',' read -ra PLS <<< "$PLATFORMS"
for p in "${PLS[@]}"; do ARGS+=(-F "platform[]=$p"); done

echo "▸ Subiendo $FILE → [$PLATFORMS] (perfil: $PROFILE)…"
RESP=$(curl -s -X POST "$BASE/upload" -H "Authorization: Apikey $UPLOAD_POST_API_KEY" "${ARGS[@]}")
echo "$RESP" | python3 -m json.tool 2>/dev/null || echo "$RESP"

RID=$(echo "$RESP" | python3 -c "import json,sys;print(json.load(sys.stdin).get('request_id',''))" 2>/dev/null || true)
[ -z "$RID" ] && exit 0
echo "▸ request_id=$RID — consultando estado…"
for i in $(seq 1 40); do
  S=$(curl -s -H "Authorization: Apikey $UPLOAD_POST_API_KEY" "$BASE/uploadposts/status?request_id=$RID")
  ST=$(echo "$S" | python3 -c "import json,sys;d=json.load(sys.stdin);print(d.get('status') or d.get('result',{}).get('status',''))" 2>/dev/null || true)
  echo "  intento $i: ${ST:-(sin estado)}"
  case "$ST" in success|completed|failed|error) echo "$S" | python3 -m json.tool 2>/dev/null; break;; esac
  sleep 8
done
