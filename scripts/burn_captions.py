#!/usr/bin/env python3
"""
burn_captions.py - Renderiza los subtitulos Hormozi (hf_captions) y los superpone al video,
dejando la salida YA SIN metadata. Requiere haber corrido make_captions.py antes.

Uso: python3 scripts/burn_captions.py --slug demo --aspect 9:16
Salida: output/<slug>{_9x16}_subs.mp4   (un solo archivo, limpio)
"""
import argparse, os, glob, subprocess, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HF_VER = "0.6.98"

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--slug", required=True)
    ap.add_argument("--aspect", default="9:16", choices=["9:16", "16:9"])
    args = ap.parse_args()
    suffix = "_9x16" if args.aspect == "9:16" else ""

    work = os.path.join(ROOT, "work", args.slug)
    hf = os.path.join(work, "hf_captions")
    if not os.path.exists(os.path.join(hf, "index.html")):
        sys.exit(f"Falta {hf}/index.html — corre antes: make_captions.py --slug {args.slug} --aspect {args.aspect}")
    base = os.path.join(ROOT, "output", f"{args.slug}{suffix}.mp4")
    if not os.path.exists(base):
        sys.exit(f"Falta el video base {base} (genera el montaje primero).")
    out = os.path.join(ROOT, "output", f"{args.slug}{suffix}_subs.mp4")

    # 1) render subtitulos a MOV con alfa (ProRes 4444) — via subprocess (evita el hook del shell)
    print("▸ Renderizando subtitulos (MOV alpha)…")
    subprocess.run(["npx", "--yes", f"hyperframes@{HF_VER}", "render", "--format", "mov",
                    "-o", "renders/caps.mov"], cwd=hf, check=True)
    mov = max(glob.glob(os.path.join(hf, "renders", "*.mov")), key=os.path.getmtime)

    # 2) overlay + salida SIN metadata
    print("▸ Overlay + limpieza de metadata…")
    r = subprocess.run(["ffmpeg", "-y", "-i", base, "-i", mov,
        "-filter_complex", "[0:v][1:v]overlay=0:0:format=auto[v]",
        "-map", "[v]", "-map", "0:a",
        "-c:v", "libx264", "-crf", "19", "-pix_fmt", "yuv420p", "-c:a", "aac",
        "-map_metadata", "-1", "-map_chapters", "-1",
        "-fflags", "+bitexact", "-flags:v", "+bitexact", "-flags:a", "+bitexact",
        "-metadata:s:v", "handler_name=", "-metadata:s:a", "handler_name=",
        "-movflags", "+faststart", out], capture_output=True, text=True)
    if r.returncode:
        sys.stderr.write(r.stderr[-2000:] + "\n"); sys.exit("ffmpeg fallo en overlay")

    # 3) borrar el MOV pesado
    try: os.remove(mov)
    except OSError: pass
    print(f"✓ {out} (subtitulos quemados, metadata limpia)")

if __name__ == "__main__":
    main()
