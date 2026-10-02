"""Build a local, synchronized source/avatar inspection viewer."""
import json
from pathlib import Path

from src.integrations.process import run_process


def encode_preview(folder: Path, ffmpeg: str = "ffmpeg", *, cancel_event=None) -> Path:
    """One portable comparison video; image sequences remain internal."""
    data = json.loads((folder / "frames.json").read_text(encoding="utf-8"))
    frames = data["frames"]
    if not frames or frames != list(range(frames[0], frames[-1] + 1)):
        raise ValueError("Preview compacto exige uma sequência completa de frames.")
    destination = folder.parent / "preview.mp4"
    temporary = folder.parent / ".preview.tmp.mp4"
    command = [str(ffmpeg), "-v", "error", "-y"]
    for pattern in ("video-%04d.jpg", "avatar-%04d.png"):
        command.extend(["-framerate", str(data["fps"]), "-start_number", str(frames[0]),
                        "-i", str(folder / pattern)])
    command.extend(["-filter_complex", "[0:v]scale=640:640:force_original_aspect_ratio=decrease,pad=640:640:(ow-iw)/2:(oh-ih)/2[v];[v][1:v]hstack=inputs=2,format=yuv420p[out]",
                    "-map", "[out]", "-frames:v", str(len(frames)), "-c:v", "libx264", "-preset", "veryfast",
                    "-crf", "22", str(temporary)])
    try:
        result = run_process(command, cwd=folder, timeout=300, cancel_event=cancel_event)
        if result.cancelled:
            raise InterruptedError("Preview cancelado.")
        if not result.succeeded or not temporary.is_file() or not temporary.stat().st_size:
            raise RuntimeError(f"Falha ao gerar preview compacto: {result.stderr[-1200:]}")
        temporary.replace(destination)
    finally:
        temporary.unlink(missing_ok=True)
    return destination


def create_preview(video: Path, folder: Path) -> Path:
    import cv2

    data = json.loads((folder / "frames.json").read_text(encoding="utf-8"))
    capture = cv2.VideoCapture(str(video))
    if not capture.isOpened():
        raise ValueError("Cannot open the source video for synchronized preview")
    try:
        next_frame = 0
        for frame in data["frames"]:
            offset = frame - data["frames"][0]
            if offset != next_frame:
                capture.set(cv2.CAP_PROP_POS_FRAMES, offset)
            ok, pixels = capture.read()
            next_frame = offset + 1
            if not ok:
                raise ValueError(f"Cannot decode preview frame {frame}")
            height, width = pixels.shape[:2]
            pixels = cv2.resize(pixels, (960, round(height * 960 / width)))
            if not cv2.imwrite(str(folder / f"video-{frame:04d}.jpg"), pixels):
                raise ValueError("Cannot write video preview")
    finally:
        capture.release()
    page = '''<!doctype html><html lang="pt-BR"><meta charset="utf-8">
<title>CP3 — inspeção sincronizada</title>
<style>body{background:#202329;color:#eee;font:18px system-ui;margin:24px}main{display:flex;align-items:center;gap:12px}main img{width:49%;object-fit:contain}input{width:70%}button{padding:8px}small{display:block}</style>
<h1>Inspeção das mãos</h1><p>Vídeo à esquerda; avatar à direita. Mão direita azul, esquerda laranja.</p>
<small>Prévia técnica em revisão. O corpo permanece estático; não há animação facial.</small>
<main><img id="video" alt="Frame do vídeo"><img id="avatar" alt="Frame do avatar"></main>
<button id="play">Reproduzir</button> <input id="seek" type="range" min="0" value="0" aria-label="Frame"><output id="time"></output>
<script>const data=__DATA__;let playing=false,last=0;const seek=document.querySelector('#seek'),button=document.querySelector('#play');seek.max=data.frames.length-1;
function show(){let i=Number(seek.value),f=data.frames[i],n=String(f).padStart(4,'0');document.querySelector('#video').src='video-'+n+'.jpg';document.querySelector('#avatar').src='avatar-'+n+'.png';document.querySelector('#time').textContent='Frame '+f+' · '+(i/data.fps).toFixed(3)+' s';}
seek.oninput=()=>{playing=false;button.textContent='Reproduzir';show()};button.onclick=()=>{playing=!playing;button.textContent=playing?'Pausar':'Reproduzir';last=performance.now()};function tick(now){if(playing&&now-last>=1000/data.fps){let steps=Math.floor((now-last)*data.fps/1000);seek.value=(Number(seek.value)+steps)%data.frames.length;last+=steps*1000/data.fps;show()}requestAnimationFrame(tick)}show();requestAnimationFrame(tick);</script></html>'''
    target = folder / "index.html"
    target.write_text(page.replace("__DATA__", json.dumps(data)), encoding="utf-8")
    return target
