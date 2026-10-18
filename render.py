"""
Tiny render service used by n8n.

POST /render  {"title": str, "voice": str, "scenes": [{"narration": str, "image_prompt": str}]}
  -> returns an MP4 (video/mp4)

Per scene: Edge TTS narration (free) + AI image from Pollinations (free, no key)
+ slow zoom effect, then all scenes are concatenated. Optional background music
is mixed in from any .mp3 files found in /music.
"""
import glob
import json
import os
import random
import shutil
import subprocess
import tempfile
import time
import traceback
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer

W, H, FPS = 1280, 720, 30
MUSIC_DIR = os.environ.get("MUSIC_DIR", "/music")
MAX_SCENES = 20
MAX_NARRATION = 700


def run(cmd):
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)


def duration(path):
    out = subprocess.check_output([
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "default=nw=1:nk=1", path,
    ])
    return float(out.strip())


def fetch_image(prompt, dest, seed):
    """Download an AI image from Pollinations. Returns True on success."""
    url = (
        "https://image.pollinations.ai/prompt/"
        + urllib.parse.quote(prompt)
        + f"?width={W}&height={H}&nologo=true&seed={seed}"
    )
    for attempt in range(4):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=120) as r:
                data = r.read()
            if len(data) > 5000:
                with open(dest, "wb") as f:
                    f.write(data)
                return True
        except Exception as e:  # network error, rate limit...
            print(f"image attempt {attempt + 1} failed: {e}", flush=True)
        time.sleep(5 * (attempt + 1))
    return False


def fallback_image(dest):
    """Plain pastel background if the image service is down."""
    color = random.choice(["0x8ecae6", "0xffb703", "0xb5e48c", "0xffafcc", "0xcdb4db"])
    run(["ffmpeg", "-y", "-f", "lavfi", "-i", f"color=c={color}:s={W}x{H}",
         "-frames:v", "1", dest])


def tts(text, voice, dest, workdir, idx):
    txt = os.path.join(workdir, f"narration_{idx}.txt")
    with open(txt, "w", encoding="utf-8") as f:
        f.write(text)
    last = None
    for attempt in range(3):
        try:
            run(["edge-tts", "--voice", voice, "--file", txt,
                 "--rate=-8%", "--write-media", dest])
            return
        except subprocess.CalledProcessError as e:
            last = e
            time.sleep(3 * (attempt + 1))
    raise RuntimeError(f"TTS failed: {last.stderr.decode(errors='ignore')[:300] if last else ''}")


def make_clip(img, audio, out, dur):
    frames = int(dur * FPS) + 1
    inc = 0.12 / frames  # reaches 1.12x zoom exactly at the end of the clip
    vf = (
        f"scale={W * 2}:{H * 2}:force_original_aspect_ratio=increase,"
        f"crop={W * 2}:{H * 2},"
        f"zoompan=z='min(zoom+{inc:.6f},1.12)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"
        f":d={frames}:s={W}x{H}:fps={FPS},format=yuv420p"
    )
    run([
        "ffmpeg", "-y", "-i", img, "-i", audio, "-vf", vf, "-af", "apad",
        "-t", f"{dur:.2f}", "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
        "-c:a", "aac", "-ar", "44100", "-ac", "2", "-r", str(FPS), out,
    ])


def render(payload):
    scenes = payload.get("scenes") or []
    voice = payload.get("voice") or "en-US-AnaNeural"
    if not scenes or len(scenes) > MAX_SCENES:
        raise ValueError(f"scenes must contain 1-{MAX_SCENES} items")

    workdir = tempfile.mkdtemp(prefix="render_")
    try:
        clips = []
        base_seed = random.randint(1, 10_000)
        for i, sc in enumerate(scenes):
            narration = str(sc.get("narration", "")).strip()[:MAX_NARRATION]
            prompt = str(sc.get("image_prompt", "")).strip() or narration
            if not narration:
                raise ValueError(f"scene {i} has no narration")

            audio = os.path.join(workdir, f"a_{i}.mp3")
            img = os.path.join(workdir, f"i_{i}.jpg")
            clip = os.path.join(workdir, f"c_{i}.mp4")

            tts(narration, voice, audio, workdir, i)
            if not fetch_image(prompt, img, base_seed + i):
                fallback_image(img)
            make_clip(img, audio, clip, duration(audio) + 0.6)
            clips.append(clip)
            print(f"scene {i + 1}/{len(scenes)} done", flush=True)

        listfile = os.path.join(workdir, "list.txt")
        with open(listfile, "w") as f:
            for c in clips:
                f.write(f"file '{c}'\n")
        joined = os.path.join(workdir, "joined.mp4")
        run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", listfile,
             "-c", "copy", joined])

        final = joined
        tracks = glob.glob(os.path.join(MUSIC_DIR, "*.mp3"))
        if tracks:
            final = os.path.join(workdir, "final.mp4")
            run([
                "ffmpeg", "-y", "-i", joined, "-stream_loop", "-1",
                "-i", random.choice(tracks),
                "-filter_complex",
                "[1:a]volume=0.12[m];[0:a][m]amix=inputs=2:duration=first:dropout_transition=0[a]",
                "-map", "0:v", "-map", "[a]", "-c:v", "copy", "-c:a", "aac", final,
            ])

        with open(final, "rb") as f:
            return f.read()
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


class Handler(BaseHTTPRequestHandler):
    def _send(self, code, body, ctype):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/health":
            self._send(200, b'{"ok":true}', "application/json")
        else:
            self._send(404, b"{}", "application/json")

    def do_POST(self):
        if self.path != "/render":
            return self._send(404, b"{}", "application/json")
        try:
            length = int(self.headers.get("Content-Length", 0))
            payload = json.loads(self.rfile.read(length) or b"{}")
            video = render(payload)
            self._send(200, video, "video/mp4")
        except Exception as e:
            traceback.print_exc()
            self._send(500, json.dumps({"error": str(e)}).encode(), "application/json")


if __name__ == "__main__":
    print("render worker listening on :5000", flush=True)
    HTTPServer(("0.0.0.0", 5000), Handler).serve_forever()
