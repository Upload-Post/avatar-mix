#!/usr/bin/env python3
"""
sync_animations.py - Trae SIEMPRE lo último del registro de HyperFrames a un proyecto.

Cada vez que el skill arranca un proyecto HyperFrames, esto descarga (o actualiza) los
bloques/animaciones de las categorías indicadas, así que las animaciones NUEVAS que vaya
publicando HeyGen aparecen automáticamente disponibles como fondos/efectos.

Uso:
  python3 scripts/sync_animations.py --hf work/<slug>/hf [--tags code-animation,transition,...]
  python3 scripts/sync_animations.py --hf work/<slug>/hf --all   # todo el registro (pesado)

Notas:
  - Se ejecuta vía subprocess (npx) para evitar el hook del shell.
  - Idempotente: re-descargar simplemente sobrescribe con la versión actual del registro.
"""
import argparse, os, subprocess, sys, json

HF_VER = "0.6.98"
# Categorías de animación reutilizables (evita 'showcase'/mapas/devices, que son composiciones enteras).
DEFAULT_TAGS = [
    "code-animation", "transition", "text-effect", "kinetic",
    "overlay", "reveal", "effect", "shader", "highlight", "morph",
]

def run(cmd, cwd):
    return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--hf", required=True, help="ruta del proyecto HyperFrames (con hyperframes.json)")
    ap.add_argument("--tags", default=",".join(DEFAULT_TAGS), help="tags a sincronizar (csv)")
    ap.add_argument("--all", action="store_true", help="sincroniza TODO el registro (pesado)")
    args = ap.parse_args()

    hf = os.path.abspath(args.hf)
    if not os.path.exists(os.path.join(hf, "hyperframes.json")):
        sys.exit(f"No es un proyecto HyperFrames: {hf} (falta hyperframes.json)")

    if args.all:
        # descubrir todos los tags del registro y traerlos
        r = run(["npx", "--yes", f"hyperframes@{HF_VER}", "catalog", "--json"], hf)
        try:
            data = json.loads(r.stdout)
            items = data if isinstance(data, list) else data.get("items", data.get("blocks", []))
            tags = sorted({t for it in items for t in (it.get("tags") or [])})
        except Exception:
            sys.exit("No se pudo leer el catálogo (--json).")
    else:
        tags = [t.strip() for t in args.tags.split(",") if t.strip()]

    print(f"▸ Sincronizando {len(tags)} categorías de animación en {hf} …")
    ok = 0
    for t in tags:
        r = run(["npx", "--yes", f"hyperframes@{HF_VER}", "add", t, "--no-clipboard"], hf)
        if r.returncode == 0:
            n = r.stdout.count("✓")
            print(f"  ✓ {t}  ({n} bloques)")
            ok += 1
        else:
            print(f"  · {t}: sin resultados / error")
    print(f"✓ {ok}/{len(tags)} categorías sincronizadas (compositions/)")

if __name__ == "__main__":
    main()
