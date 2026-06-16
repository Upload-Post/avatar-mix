#!/usr/bin/env python3
"""
make_bg.py - Genera el video de FONDO por escena: work/<slug>/bg/<id>.mp4 (1920x1080).

Dos modos:
  --mode card        (DEFAULT) tarjetas de marca renderizadas con Pillow (PNG) -> video.
                     Sin depender de drawtext/freetype en ffmpeg. Pipeline garantizado.
  --mode hyperframes Renderiza la composicion HyperFrames (work/<slug>/composition.html)
                     y la trocea por escena. Requiere `npx hyperframes` + el array SCENES
                     ya inyectado con start/duration coincidentes con las duraciones reales.

Requisito comun: cada escena en script.json debe tener "duration" (segundos), que el
orquestador rellena con ffprobe de los clips de avatar ya generados.

Uso:
  python3 scripts/make_bg.py --slug demo [--mode card|hyperframes]
"""
import argparse, json, os, subprocess, sys, glob
from PIL import Image, ImageDraw, ImageFont

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
W, H, FPS = 1920, 1080, 30
BGDIR = "bg"

FONT_DIRS = ["/System/Library/Fonts/Supplemental", "/Library/Fonts", "/System/Library/Fonts"]
def find_font(*names):
    for n in names:
        for d in FONT_DIRS:
            p = os.path.join(d, n)
            if os.path.exists(p):
                return p
    return None
FONT_BOLD = find_font("Arial Bold.ttf", "Helvetica.ttc", "Arial.ttf")
FONT_REG = find_font("Arial.ttf", "Helvetica.ttc", "Arial Bold.ttf")

def run(cmd):
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        sys.stderr.write(r.stderr[-3000:] + "\n")
        raise SystemExit("ffmpeg/hyperframes fallo")
    return r

def load_json(p):
    with open(p) as f:
        return json.load(f)

def hexrgb(c, default="#0b0f1a"):
    c = (c or default).lstrip("#")
    return tuple(int(c[i:i+2], 16) for i in (0, 2, 4))

def fnt(path, size):
    return ImageFont.truetype(path, size)

def wrap(draw, text, font, max_w):
    words, lines, cur = text.split(), [], ""
    for w in words:
        t = (cur + " " + w).strip()
        if draw.textlength(t, font=font) <= max_w:
            cur = t
        else:
            if cur:
                lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines

def render_card_png(scene, cfg, out_png):
    brand = cfg.get("brand", {})
    bg = hexrgb(brand.get("bg_color", "#0b0f1a"))
    accent = hexrgb(brand.get("accent", "#3ddc97"))
    text_c = hexrgb(brand.get("text_color", "#ffffff"), "#ffffff")
    muted = (180, 185, 195)
    bv = scene.get("bg_visual", {}) or {}
    style = bv.get("style", "title_card")

    # Tamanos proporcionales -> funciona en 16:9 y 9:16.
    base = min(W, H)
    M = int(W * 0.08)
    HL = int(base * 0.092); SUB = int(base * 0.046); BUL = int(base * 0.05)
    barw = int(base * 0.157); barh = int(base * 0.0148); step = int(base * 0.096)

    img = Image.new("RGB", (W, H), bg)
    glow = Image.new("RGB", (W, H), bg)
    gd = ImageDraw.Draw(glow)
    gd.ellipse([W-int(W*0.34), -int(H*0.18), W+int(W*0.13), int(H*0.37)], fill=accent)
    img = Image.blend(img, glow, 0.10)
    d = ImageDraw.Draw(img)

    headline = bv.get("headline", "")
    subline = bv.get("subline", "")
    bullets = bv.get("bullets", []) or []

    if style == "fullbleed":
        f_h = fnt(FONT_BOLD, int(base * 0.11))
        lines = wrap(d, headline, f_h, W - 2*M)
        total_h = sum(f_h.size + 24 for _ in lines)
        y = (H - total_h)//2 - int(H*0.04)
        for ln in lines:
            tw = d.textlength(ln, font=f_h)
            d.text(((W-tw)//2, y), ln, font=f_h, fill=text_c)
            y += f_h.size + 24
        if subline:
            f_s = fnt(FONT_REG, SUB)
            tw = d.textlength(subline, font=f_s)
            d.text(((W-tw)//2, y+20), subline, font=f_s, fill=muted)
    else:
        ytop = int(H * 0.30)
        d.rounded_rectangle([M, ytop, M+barw, ytop+barh], radius=8, fill=accent)
        f_h = fnt(FONT_BOLD, HL)
        lines = wrap(d, headline, f_h, W - 2*M)
        y = ytop + int(barh*2.5)
        for ln in lines:
            d.text((M, y), ln, font=f_h, fill=text_c)
            y += f_h.size + 12
        if style == "bullets":
            f_b = fnt(FONT_BOLD, BUL)
            y = y + int(base*0.04)
            for b in bullets:
                d.rounded_rectangle([M, y+12, M+34, y+46], radius=8, fill=accent)
                d.text((M+64, y), b, font=f_b, fill=text_c)
                y += step
        elif subline:
            f_s = fnt(FONT_REG, SUB)
            d.text((M, y+24), subline, font=f_s, fill=muted)

    img.save(out_png)

def gen_card(scene, cfg, work):
    sid = scene["id"]
    dur = float(scene["duration"])
    bgdir = os.path.join(work, BGDIR); os.makedirs(bgdir, exist_ok=True)
    tmp = os.path.join(work, ".bgtmp"); os.makedirs(tmp, exist_ok=True)
    png = os.path.join(tmp, f"{sid}.png")
    out = os.path.join(bgdir, f"{sid}.mp4")
    render_card_png(scene, cfg, png)
    # PNG -> video con un suave zoom (Ken Burns) para que no sea estatico
    run(["ffmpeg", "-y", "-loop", "1", "-i", png, "-t", f"{dur:.3f}",
         "-vf", f"scale={W*1.06:.0f}:-1,zoompan=z='min(zoom+0.0006,1.06)':d={int(dur*FPS)}:"
                f"s={W}x{H}:fps={FPS},setsar=1",
         "-pix_fmt", "yuv420p", "-c:v", "libx264", "-crf", "20", out])
    print(f"  bg escena {sid} [card/{(scene.get('bg_visual') or {}).get('style','title_card')}] -> {dur:.2f}s")
    return out

HF_VER = "0.6.98"

def render_hyperframes(work, scenes):
    # Proyecto HyperFrames en work/<slug>/hf/ (scaffold con `npx hyperframes init` y
    # luego copiar templates/composition.html a hf/index.html e inyectar SCENES con
    # start acumulado + duration por escena).
    hf = os.path.join(work, "hf_9x16" if H > W else "hf")
    comp = os.path.join(hf, "index.html")
    if not os.path.exists(comp):
        raise SystemExit(f"Falta {comp}. Scaffold: `npx hyperframes init hf` dentro de {work} "
                         f"y copia templates/composition.html a hf/index.html con SCENES inyectado.")
    # Traer SIEMPRE lo último del registro (animaciones nuevas) — una vez por proyecto.
    if os.environ.get("HF_NO_SYNC") != "1" and not os.path.exists(os.path.join(hf, ".animations_synced")):
        sync = os.path.join(ROOT, "scripts", "sync_animations.py")
        if os.path.exists(sync):
            subprocess.run(["python3", sync, "--hf", hf])
            open(os.path.join(hf, ".animations_synced"), "w").close()
    print("› Renderizando HyperFrames…")
    subprocess.run(["npx", "--yes", f"hyperframes@{HF_VER}", "render"], cwd=hf, check=True)
    cands = glob.glob(os.path.join(hf, "renders", "*.mp4"))
    if not cands:
        raise SystemExit("HyperFrames no produjo MP4 en hf/renders/.")
    master = max(cands, key=os.path.getmtime)
    bgdir = os.path.join(work, BGDIR); os.makedirs(bgdir, exist_ok=True)
    start = 0.0
    for sc in scenes:
        dur = float(sc["duration"])
        out = os.path.join(bgdir, f"{sc['id']}.mp4")
        run(["ffmpeg", "-y", "-ss", f"{start:.3f}", "-t", f"{dur:.3f}", "-i", master,
             "-c:v", "libx264", "-crf", "19", "-pix_fmt", "yuv420p", out])
        print(f"  bg escena {sc['id']} [hyperframes @ {start:.2f}s] -> {dur:.2f}s")
        start += dur

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--slug", required=True)
    ap.add_argument("--mode", choices=["card", "hyperframes"], default="card")
    ap.add_argument("--aspect", default="16:9", choices=["16:9", "9:16"],
                    help="16:9 (horizontal) o 9:16 (vertical/movil)")
    args = ap.parse_args()

    global W, H, BGDIR
    W, H = (1080, 1920) if args.aspect == "9:16" else (1920, 1080)
    BGDIR = "bg_9x16" if args.aspect == "9:16" else "bg"

    work = os.path.join(ROOT, "work", args.slug)
    cfg = load_json(os.path.join(ROOT, "config", "avatar.json"))
    scenes = load_json(os.path.join(work, "script.json"))["scenes"]
    for sc in scenes:
        if "duration" not in sc:
            raise SystemExit(f"Escena {sc['id']} sin 'duration'. Mide el clip de avatar "
                             f"con ffprobe y rellena script.json antes de generar fondos.")

    if args.mode == "card":
        if not FONT_BOLD:
            raise SystemExit("No se encontro fuente TTF (Arial/Helvetica).")
        for sc in scenes:
            gen_card(sc, cfg, work)
    else:
        render_hyperframes(work, scenes)
    print("✓ Fondos generados en", os.path.join(work, BGDIR))

if __name__ == "__main__":
    main()
