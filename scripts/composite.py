#!/usr/bin/env python3
"""
composite.py - El "editor" del pipeline avatar-mix.

Toma los clips de avatar (HeyGen) y los fondos (HyperFrames) de una escena
y construye el montaje dinamico 16:9 con:
  - modo fullscreen : avatar a pantalla completa
  - modo corner     : fondo full + avatar chroma-keyed abajo-derecha (esquinas redondeadas)
  - modo bg_only    : solo fondo (la voz del avatar sigue como locucion)
  - transiciones encadenadas (xfade) + audio (acrossfade)
  - mezcla opcional de musica con ducking (sidechaincompress)

Entradas (relativas a la raiz del proyecto):
  work/<slug>/script.json
  work/<slug>/clips/avatar_<id>.mp4     (uno por escena; en corner, idealmente fondo verde)
  work/<slug>/bg/<id>.mp4               (requerido en corner y bg_only)
  config/avatar.json
Salida:
  output/<slug>.mp4

Uso:
  python3 scripts/composite.py --slug demo [--music assets/music.mp3] [--keep-temp]
"""
import argparse, json, os, subprocess, sys, tempfile, shutil

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
W, H, FPS = 1920, 1080, 30
BGDIR = "bg"

def run(cmd):
    print("›", " ".join(cmd[:6]), "…" if len(cmd) > 6 else "")
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        sys.stderr.write(r.stderr[-3000:] + "\n")
        raise SystemExit(f"ffmpeg fallo (code {r.returncode})")
    return r

def ffprobe_dur(path):
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=nk=1:nw=1", path],
        capture_output=True, text=True)
    return float(r.stdout.strip())

def load_json(p):
    with open(p) as f:
        return json.load(f)

def scene_path(tmp, sid):
    return os.path.join(tmp, f"scene_{sid}.mp4")

def build_scene(scene, cfg, work, tmp):
    """Renderiza una escena normalizada (1920x1080, 30fps, aac) a scene_<id>.mp4."""
    sid = scene["id"]
    mode = scene["mode"]
    clip_id = scene.get("clip", sid)             # clip de origen (permite compartir un clip entre escenas)
    clip_in = float(scene.get("clip_in", 0))     # recorte: segundos a saltar al inicio del clip
    avatar = os.path.join(work, "clips", f"avatar_{clip_id}.mp4")
    bg = os.path.join(work, BGDIR, f"{sid}.mp4")
    out = scene_path(tmp, sid)
    if not os.path.exists(avatar):
        raise SystemExit(f"Falta clip de avatar: {avatar}")
    dur = float(scene.get("duration") or ffprobe_dur(avatar))
    # input del avatar con recorte opcional (-ss antes de -i = seek rapido)
    av_in = (["-ss", f"{clip_in:.3f}"] if clip_in > 0 else []) + ["-i", avatar]

    cover = f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},setsar=1,fps={FPS}"
    pad = (f"scale={W}:{H}:force_original_aspect_ratio=decrease,"
           f"pad={W}:{H}:(ow-iw)/2:(oh-ih)/2:color=black,setsar=1,fps={FPS}")

    if mode == "fullscreen":
        # cover = rellena el frame (en vertical hace zoom al centro, look reels);
        # en 16:9 con clip 16:9 equivale a encaje exacto.
        vf = f"[0:v]{cover}[v]"
        cmd = ["ffmpeg", "-y"] + av_in + \
              ["-filter_complex", vf, "-map", "[v]", "-map", "0:a?", "-t", f"{dur:.3f}"]

    elif mode == "bg_only":
        if not os.path.exists(bg):
            raise SystemExit(f"Falta fondo para escena {sid}: {bg}")
        vf = f"[1:v]{cover},trim=duration={dur:.3f},setpts=PTS-STARTPTS[v]"
        cmd = ["ffmpeg", "-y"] + av_in + ["-stream_loop", "-1", "-i", bg,
               "-filter_complex", vf, "-map", "[v]", "-map", "0:a?", "-t", f"{dur:.3f}"]

    elif mode == "corner":
        if not os.path.exists(bg):
            raise SystemExit(f"Falta fondo para escena {sid}: {bg}")
        # esquina con tamaño propio en vertical (PiP mas grande)
        cn = cfg.get("corner_9x16", cfg["corner"]) if H > W else cfg["corner"]
        cw = int(W * cn["scale_width_pct"] / 100)          # ancho del recuadro PiP
        r = cn.get("corner_radius_px", 0)
        m = cn.get("margin_px", 48)
        b = cn.get("border_px", 0)
        bcol = cn.get("border_color", "white")
        pos = cn.get("position", "bottom-right")
        inner = cw - 2 * b
        # Recuadro "webcam": el avatar con SU PROPIO fondo, escalado a la esquina.
        # Sin chroma-key. Opcional: borde (pad) + esquinas redondeadas (mascara alpha).
        chain = f"[0:v]scale={inner}:-1"
        if b > 0:
            chain += f",pad=iw+{2*b}:ih+{2*b}:{b}:{b}:color={bcol}"
        if r > 0:
            chain += (f",format=yuva420p,geq=r='r(X,Y)':g='g(X,Y)':b='b(X,Y)':a='"
                      f"if( ("
                      f"lt(X\\,{r})*lt(Y\\,{r})*gt(hypot({r}-X\\,{r}-Y)\\,{r}) +"
                      f"gt(X\\,W-{r})*lt(Y\\,{r})*gt(hypot(X-(W-{r})\\,{r}-Y)\\,{r}) +"
                      f"lt(X\\,{r})*gt(Y\\,H-{r})*gt(hypot({r}-X\\,Y-(H-{r}))\\,{r}) +"
                      f"gt(X\\,W-{r})*gt(Y\\,H-{r})*gt(hypot(X-(W-{r})\\,Y-(H-{r}))\\,{r})"
                      f") , 0 , 255)'")
        ox = f"(W-w)/2" if pos == "bottom-center" else f"W-w-{m}"
        vf = (
            f"[1:v]{cover},trim=duration={dur:.3f},setpts=PTS-STARTPTS[bgv];"
            f"{chain}[fg];"
            f"[bgv][fg]overlay={ox}:H-h-{m}:format=auto[v]"
        )
        cmd = ["ffmpeg", "-y"] + av_in + ["-stream_loop", "-1", "-i", bg,
               "-filter_complex", vf, "-map", "[v]", "-map", "0:a?", "-t", f"{dur:.3f}"]
    else:
        raise SystemExit(f"Modo desconocido en escena {sid}: {mode}")

    # Normaliza salida (mismo codec/fps/audio) para poder encadenar xfade despues.
    cmd += ["-c:v", "libx264", "-preset", "medium", "-crf", "19", "-pix_fmt", "yuv420p",
            "-r", str(FPS), "-c:a", "aac", "-ar", "48000", "-ac", "2",
            "-af", "aresample=async=1:first_pts=0", out]
    run(cmd)
    return out, dur

def xfade_map(t):
    return {"fade": "fade", "slide": "slideleft", "dissolve": "dissolve",
            "wipe": "wiperight", "cut": "fade"}.get(t, "fade")

def compute_overlaps(scenes, durs):
    """Solape (s) de cada transicion entre escena i e i+1."""
    overlaps = []
    for i in range(len(durs) - 1):
        t = scenes[i].get("transition", "fade")
        o = scenes[i].get("transition_after_sec", 0.5)
        if t == "cut" or o <= 0:
            o = 1.0 / FPS                      # cut = crossfade de 1 frame ~ corte seco
        o = min(o, durs[i] - 0.05, durs[i + 1] - 0.05)
        overlaps.append(max(o, 1.0 / FPS))
    return overlaps

def final_starts(durs, overlaps):
    """Tiempo de inicio de cada escena en la timeline final (tras encadenar)."""
    starts = [0.0]
    for i in range(len(durs) - 1):
        starts.append(starts[-1] + durs[i] - overlaps[i])
    return starts

def chain_transitions(scenes, paths, durs, overlaps, tmp):
    """Encadena escenas con xfade (video) + acrossfade (audio) en una sola pasada."""
    n = len(paths)
    out = os.path.join(tmp, "chained.mp4")
    if n == 1:
        shutil.copy(paths[0], out)
        return out

    inputs = []
    for p in paths:
        inputs += ["-i", p]

    fc = []
    vlab, alab = "0:v", "0:a"
    running = durs[0]
    for i in range(n - 1):
        o = overlaps[i]
        offset = running - o
        nv, na = f"vx{i}", f"ax{i}"
        fc.append(f"[{vlab}][{i+1}:v]xfade=transition={xfade_map(scenes[i].get('transition','fade'))}:"
                  f"duration={o:.3f}:offset={offset:.3f}[{nv}]")
        fc.append(f"[{alab}][{i+1}:a]acrossfade=d={o:.3f}:c1=tri:c2=tri[{na}]")
        vlab, alab = nv, na
        running = offset + durs[i + 1]

    cmd = ["ffmpeg", "-y"] + inputs + [
        "-filter_complex", ";".join(fc),
        "-map", f"[{vlab}]", "-map", f"[{alab}]",
        "-c:v", "libx264", "-preset", "medium", "-crf", "19", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-ar", "48000", "-ac", "2", out]
    run(cmd)
    return out

def strip_meta(src, dst):
    """Copia sin recodificar quitando metadata (encoder/fecha/handler)."""
    run(["ffmpeg", "-y", "-i", src, "-map_metadata", "-1", "-map_chapters", "-1",
         "-fflags", "+bitexact", "-flags:v", "+bitexact", "-flags:a", "+bitexact",
         "-metadata:s:v", "handler_name=", "-metadata:s:a", "handler_name=",
         "-c", "copy", "-movflags", "+faststart", dst])

def mix_audio(video, music, events, cfg, out):
    """Mezcla la voz (del video) + musica con ducking + SFX puntuales.
    events = lista de (time_seg, ruta_sfx, gain_db)."""
    a = cfg.get("audio", {})
    vol = a.get("music_volume_db", -22)
    thr = a.get("duck_threshold", 0.05)
    ratio = a.get("duck_ratio", 8)
    events = [e for e in events if e[1] and os.path.exists(e[1])]
    if not music and not events:
        shutil.copy(video, out); return

    inputs = ["-i", video]
    fc = []
    mix_labels = []

    # Voz: se separa si hay musica (una copia para el sidechain).
    if music:
        fc.append("[0:a]asplit=2[va][vk]")
        voice_main = "[va]"; voice_key = "[vk]"
    else:
        voice_main = "[0:a]"
    mix_labels.append(voice_main)

    if music:
        mi = inputs.count("-i")
        inputs += ["-stream_loop", "-1", "-i", music]
        fc.append(f"[{mi}:a]volume={vol}dB[m]")
        fc.append(f"[m]{voice_key}sidechaincompress=threshold={thr}:ratio={ratio}:"
                  f"attack=20:release=400[duck]")
        mix_labels.append("[duck]")

    # SFX: un input por fichero distinto, asplit por nº de usos.
    files = {}
    for _, f, _g in events:
        files.setdefault(f, 0)
        files[f] += 1
    file_idx, file_lbls = {}, {}
    for f, k in files.items():
        idx = len([x for x in inputs if x == "-i"])  # nº de inputs hasta ahora
        inputs += ["-i", f]
        file_idx[f] = idx
        if k == 1:
            file_lbls[f] = [f"{idx}:a"]
        else:
            outs = [f"f{idx}_{j}" for j in range(k)]
            fc.append(f"[{idx}:a]asplit={k}" + "".join(f"[{o}]" for o in outs))
            file_lbls[f] = outs
    used = {f: 0 for f in files}
    for n, (t, f, g) in enumerate(events):
        lbl = file_lbls[f][used[f]]; used[f] += 1
        ms = max(0, int(t * 1000))
        sl = f"s{n}"
        fc.append(f"[{lbl}]adelay={ms}|{ms},volume={g}dB[{sl}]")
        mix_labels.append(f"[{sl}]")

    ninputs = len(mix_labels)
    fc.append("".join(mix_labels) +
              f"amix=inputs={ninputs}:duration=first:normalize=0:dropout_transition=0[mx]")
    fc.append("[mx]alimiter=limit=0.95[aout]")

    dur = ffprobe_dur(video)   # duracion real (robusto ante metadata de stream rara del xfade)
    run(["ffmpeg", "-y"] + inputs + [
        "-filter_complex", ";".join(fc), "-map", "0:v", "-map", "[aout]",
        "-c:v", "copy", "-c:a", "aac", "-ar", "48000", "-t", f"{dur:.3f}", out])

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--slug", required=True)
    ap.add_argument("--music", default=None, help="ruta a musica de fondo (opcional)")
    ap.add_argument("--whoosh", default=None, help="SFX en cada transicion (opcional)")
    ap.add_argument("--pop", default=None, help="SFX al revelar escenas corner/bullets (opcional)")
    ap.add_argument("--sfx-manifest", default=None, dest="sfx_manifest",
                    help="JSON con SFX contextuales: [{scene|at, offset, file, gain_db}]")
    ap.add_argument("--aspect", default="16:9", choices=["16:9", "9:16"],
                    help="formato de salida: 16:9 (horizontal) o 9:16 (vertical/movil)")
    ap.add_argument("--keep-temp", action="store_true")
    args = ap.parse_args()

    global W, H, BGDIR
    W, H = (1080, 1920) if args.aspect == "9:16" else (1920, 1080)
    BGDIR = "bg_9x16" if args.aspect == "9:16" else "bg"

    work = os.path.join(ROOT, "work", args.slug)
    cfg = load_json(os.path.join(ROOT, "config", "avatar.json"))
    script = load_json(os.path.join(work, "script.json"))
    scenes = script["scenes"]

    suffix = "" if args.aspect == "16:9" else "_9x16"
    out_final = os.path.join(ROOT, "output", f"{args.slug}{suffix}.mp4")
    os.makedirs(os.path.join(ROOT, "output"), exist_ok=True)
    tmp = tempfile.mkdtemp(prefix=f"avmix_{args.slug}_", dir=work)

    try:
        paths, durs = [], []
        for sc in scenes:
            p, d = build_scene(sc, cfg, work, tmp)
            paths.append(p); durs.append(d)
            print(f"  escena {sc['id']} [{sc['mode']}] -> {d:.2f}s")

        overlaps = compute_overlaps(scenes, durs)
        chained = chain_transitions(scenes, paths, durs, overlaps, tmp)

        # Eventos de SFX en la timeline final.
        starts = final_starts(durs, overlaps)
        events = []
        if args.whoosh and os.path.exists(args.whoosh):
            for i in range(1, len(scenes)):                 # whoosh en cada transicion
                events.append((max(0.0, starts[i] - 0.12), args.whoosh, -7))
        if args.pop and os.path.exists(args.pop):
            for i, sc in enumerate(scenes):                 # pop al revelar corner/bullets
                style = (sc.get("bg_visual") or {}).get("style")
                if sc.get("mode") == "corner" or style == "bullets":
                    events.append((starts[i] + 0.35, args.pop, -11))

        # SFX contextuales por escena (manifiesto generado por el skill).
        id2idx = {sc["id"]: i for i, sc in enumerate(scenes)}
        if args.sfx_manifest and os.path.exists(args.sfx_manifest):
            for e in load_json(args.sfx_manifest):
                if not e.get("file") or not os.path.exists(e["file"]):
                    continue
                off = float(e.get("offset", 0.0))
                if "scene" in e and e["scene"] in id2idx:
                    t = starts[id2idx[e["scene"]]] + off
                elif "at" in e:
                    t = float(e["at"]) + off
                else:
                    continue
                events.append((max(0.0, t), e["file"], float(e.get("gain_db", -9))))

        music = args.music if (args.music and os.path.exists(args.music)) else None
        pre = os.path.join(tmp, "pre_final.mp4")
        if music or events:
            mix_audio(chained, music, events, cfg, pre)
        else:
            shutil.copy(chained, pre)
        # salida final SIN metadata (encoder/fecha/handler) — un solo archivo limpio
        strip_meta(pre, out_final)

        print(f"\n✓ Listo: {out_final}  ({ffprobe_dur(out_final):.1f}s)  "
              f"[musica={'si' if music else 'no'}, sfx={len(events)}, metadata=limpia]")
    finally:
        if not args.keep_temp:
            shutil.rmtree(tmp, ignore_errors=True)

if __name__ == "__main__":
    main()
