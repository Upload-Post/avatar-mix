#!/usr/bin/env python3
"""
make_captions.py - Genera subtitulos estilo Hormozi como overlay transparente (HyperFrames).

Flujo:
  1. Lee work/<slug>/transcripts/avatar_<id>.json (whisper word-level) y script.json (duraciones).
  2. Mapea los tiempos de cada palabra al timeline FINAL (offset por escena, con solapes de transicion).
  3. Agrupa en lineas cortas (Hormozi) y genera work/<slug>/hf_captions/index.html (bg transparente):
     frases en mayusculas, grandes, con la palabra activa resaltada en acento + pop.
  Luego: render --format webm (alpha) y overlay con FFmpeg (ver add_captions).

Uso: python3 scripts/make_captions.py --slug demo --aspect 9:16
"""
import argparse, json, os, glob, html

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FPS = 30

def load(p):
    with open(p) as f: return json.load(f)

def overlaps(scenes, durs):
    o = []
    for i in range(len(durs)-1):
        t = scenes[i].get("transition","fade"); v = scenes[i].get("transition_after_sec",0.5)
        if t == "cut" or v <= 0: v = 1.0/FPS
        v = min(v, durs[i]-0.05, durs[i+1]-0.05)
        o.append(max(v, 1.0/FPS))
    return o

def starts(durs, ov):
    s=[0.0]
    for i in range(len(durs)-1): s.append(s[-1]+durs[i]-ov[i])
    return s

def clean(w):
    return w.strip()

def chunk_words(words, max_words=3, max_gap=0.45):
    """Agrupa palabras en lineas cortas; corta por nº, pausa o puntuacion fuerte."""
    lines=[]; cur=[]
    for i,w in enumerate(words):
        cur.append(w)
        txt=w["t"]
        hard = txt.endswith((".","?","!",":"))
        gap_next = (words[i+1]["start"]-w["end"]) if i+1<len(words) else 99
        if len(cur)>=max_words or hard or gap_next>max_gap:
            lines.append(cur); cur=[]
    if cur: lines.append(cur)
    return lines

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--slug",required=True)
    ap.add_argument("--aspect",default="9:16",choices=["9:16","16:9"])
    args=ap.parse_args()
    W,H=(1080,1920) if args.aspect=="9:16" else (1920,1080)
    capY = int(H*0.60) if args.aspect=="9:16" else int(H*0.74)

    work=os.path.join(ROOT,"work",args.slug)
    scenes=load(os.path.join(work,"script.json"))["scenes"]
    durs=[float(s["duration"]) for s in scenes]
    ov=overlaps(scenes,durs); st=starts(durs,ov)

    # Fuente de palabras: captions_src.json (word_timestamps de HeyGen create_speech).
    src=load(os.path.join(work,"captions_src.json"))
    by_id={s["id"]:s for s in src["scenes"]}
    allwords=[]
    for i,sc in enumerate(scenes):
        s=by_id.get(sc["id"])
        if not s: continue
        tts=float(s.get("tts_dur") or durs[i])
        # escala para encajar el habla TTS en la duracion real del clip
        f=min(1.0, durs[i]/tts) if tts>0 else 1.0
        for w in s["words"]:
            t=clean(w.get("t",""))
            if not t: continue
            allwords.append({"t":t,
                "start":round(st[i]+float(w["start"])*f,3),
                "end":round(st[i]+float(w["end"])*f,3)})

    total=round(st[-1]+durs[-1],2)
    lines=chunk_words(allwords)

    # construir SCENES de captions
    cap=[]
    for ln in lines:
        s0=ln[0]["start"]-0.08; e0=ln[-1]["end"]+0.18
        cap.append({"start":round(max(0,s0),3),"dur":round(e0-max(0,s0),3),
                    "words":[{"t":w["t"].upper(),"a":round(w["start"],3),"b":round(w["end"],3)} for w in ln]})

    # evitar solape entre lineas consecutivas (cada linea termina antes de que empiece la siguiente)
    for i in range(len(cap)-1):
        nxt=cap[i+1]["start"]
        end=cap[i]["start"]+cap[i]["dur"]
        if end > nxt-0.02:
            cap[i]["dur"]=round(max(0.3, nxt-0.02-cap[i]["start"]),3)

    capjson=json.dumps(cap,ensure_ascii=False)
    htmlout=TEMPLATE.replace("__W__",str(W)).replace("__H__",str(H)).replace("__CAPY__",str(capY)) \
        .replace("__TOTAL__",str(total)).replace("__CAP__",capjson)
    outdir=os.path.join(work,"hf_captions"); os.makedirs(outdir,exist_ok=True)
    # scaffold minimo (copia de hf)
    for f in ("package.json","hyperframes.json","meta.json"):
        src=os.path.join(work,"hf",f)
        if os.path.exists(src) and not os.path.exists(os.path.join(outdir,f)):
            import shutil; shutil.copy(src,os.path.join(outdir,f))
    open(os.path.join(outdir,"index.html"),"w",encoding="utf-8").write(htmlout)
    print(f"✓ {len(cap)} lineas de subtitulos → {outdir}/index.html (total {total}s)")

TEMPLATE = r"""<!doctype html>
<html lang="es"><head><meta charset="UTF-8"/>
<meta name="viewport" content="width=__W__, height=__H__"/>
<script src="https://cdn.jsdelivr.net/npm/gsap@3.14.2/dist/gsap.min.js"></script>
<style>
  *{margin:0;padding:0;box-sizing:border-box}
  html,body{width:__W__px;height:__H__px;overflow:hidden;background:transparent}
  body{font-family:"Inter",system-ui,sans-serif}
  #root{position:relative;width:__W__px;height:__H__px;background:transparent}
  .clip{position:absolute}
  .line{left:8%;width:84%;top:__CAPY__px;display:flex;flex-wrap:wrap;justify-content:center;
        gap:18px 22px;text-align:center}
  .w{font-size:104px;font-weight:800;letter-spacing:-1px;color:#fff;line-height:1.05;
     text-transform:uppercase;
     text-shadow:0 6px 18px rgba(0,0,0,.85), 0 0 4px rgba(0,0,0,.9);
     -webkit-text-stroke:3px rgba(0,0,0,.55);display:inline-block}
</style></head>
<body>
<div id="root" data-composition-id="main" data-start="0" data-duration="__TOTAL__"
     data-width="__W__" data-height="__H__"></div>
<script>
const CAP=__CAP__;
const root=document.getElementById("root");
window.__timelines=window.__timelines||{};
const M=gsap.timeline({paused:true});
CAP.forEach((ln,i)=>{
  const d=document.createElement("div");
  d.className="clip line"; d.id="ln"+i;
  d.dataset.start=ln.start; d.dataset.duration=ln.dur; d.dataset.trackIndex=1;
  ln.words.forEach((w,j)=>{const sp=document.createElement("span");sp.className="w";sp.id="w"+i+"_"+j;sp.textContent=w.t;d.appendChild(sp);});
  root.appendChild(d);
  // entrada de la linea (pop)
  M.fromTo("#ln"+i,{opacity:0,scale:.7,y:30},{opacity:1,scale:1,y:0,duration:.22,ease:"back.out(2)"},ln.start);
  M.to("#ln"+i,{opacity:0,duration:.12,ease:"power1.in"},ln.start+ln.dur-0.12);
  // resaltado por palabra
  ln.words.forEach((w,j)=>{
    M.to("#w"+i+"_"+j,{color:"#3ddc97",scale:1.14,duration:.06,ease:"power2.out"},w.a);
    M.to("#w"+i+"_"+j,{color:"#ffffff",scale:1.0,duration:.12,ease:"power1.out"},w.b+0.02);
  });
});
window.__timelines["main"]=M;
</script></body></html>
"""

if __name__=="__main__":
    main()
