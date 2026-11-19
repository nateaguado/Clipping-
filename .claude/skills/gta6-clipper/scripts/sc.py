"""Shared helpers: where the tools are, running ffmpeg, timing estimates."""
import json, os, subprocess, sys, time

# Windows prints through an old code page by default; emoji or non-English words in a transcript would crash it
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

# ffmpeg only reads http_proxy (even for https links); behind an HTTPS proxy it would otherwise fail to reach anything
if os.environ.get('HTTPS_PROXY') and not os.environ.get('http_proxy'):
    os.environ['http_proxy'] = os.environ['HTTPS_PROXY']

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL = os.path.dirname(HERE)
TOOLS = os.path.join(os.path.expanduser('~'), '.stream-clipper')
CONF = os.path.join(TOOLS, 'config.json')
FPS = 30
W, H = 1080, 1920


def jload(path):
    with open(path, encoding='utf-8') as f:
        return json.load(f)


def write_text(path, text):
    with open(path, 'w', encoding='utf-8') as f:
        f.write(text)


def imwrite(path, img, params=()):
    """cv2.imwrite cannot write to folders with accents or emoji in their name on Windows; this can."""
    ok, buf = __import__('cv2').imencode(os.path.splitext(path)[1] or '.jpg', img, list(params))
    if ok:
        with open(path, 'wb') as f:
            f.write(buf.tobytes())
    return ok


def conf():
    try:
        return jload(CONF)
    except Exception:
        raise SystemExit('The clipper is not set up yet. Run scripts/setup.sh first.')


def _ffmpeg_on_path():
    """The speech reader (mlx-whisper / faster-whisper) calls plain `ffmpeg`, so the private ffmpeg that setup downloaded
    must be on PATH for it, even on a computer that has no ffmpeg of its own."""
    try:
        d = os.path.dirname(jload(CONF)['ffmpeg'])
    except Exception:
        return
    if d and d not in os.environ.get('PATH', '').split(os.pathsep):
        os.environ['PATH'] = d + os.pathsep + os.environ.get('PATH', '')


def save_conf(c):
    jdump(c, CONF)


def FF():
    return conf()['ffmpeg']


def FP():
    return conf()['ffprobe']


def run(*a, quiet=True):
    r = subprocess.run([str(x) for x in a], capture_output=quiet)
    if r.returncode:
        err = (r.stderr or b'').decode(errors='replace')[-1500:] if quiet else ''
        raise SystemExit(f'command failed: {a[0]} ...\n{err}')
    return r


def probe(path):
    out = subprocess.check_output([FP(), '-v', 'error', '-show_entries', 'stream=codec_type,width,height,r_frame_rate:format=duration:stream_side_data=rotation',
                                   '-of', 'json', path]).decode()
    d = json.loads(out)
    v = next((s for s in d.get('streams', []) if s.get('codec_type') == 'video'), {})
    a = any(s.get('codec_type') == 'audio' for s in d.get('streams', []))
    num, _, den = (v.get('r_frame_rate') or '30/1').partition('/')
    w, h = int(v.get('width', 0)), int(v.get('height', 0))
    rot = 0
    for sd in v.get('side_data_list', []) or []:
        rot = int(sd.get('rotation', 0) or 0)
    if abs(rot) == 90:
        w, h = h, w
    return dict(w=w, h=h, fps=float(num) / float(den or 1), dur=float(d.get('format', {}).get('duration', 0)), audio=a)


def face_detector(w, h, score=.7):
    """The face finder. The model is handed over from memory: OpenCV cannot open files in folders with accents or
    emoji in their name on Windows."""
    import cv2, numpy as np
    buf = np.fromfile(os.path.join(SKILL, 'models', 'face_detection_yunet_2023mar.onnx'), np.uint8)
    return cv2.FaceDetectorYN.create('onnx', buf, np.array([], np.uint8), (w, h), score)


def human_time(sec):
    sec = max(5, int(round(sec / 5.0) * 5))
    if sec < 60:
        return f'about {sec} seconds'
    m = sec / 60
    return f'about {round(m)} minute{"s" if round(m) != 1 else ""}' if m < 90 else f'about {m / 60:.1f} hours'


# --- time estimates. Each job stores how long it took per second of video, so estimates get better with use.
DEFAULTS = {'analyze': 6.0, 'prep': 1.5, 'render': 3.0}  # Apple M1-class speeds; replaced by real ones after the first job


def estimate(job, seconds_of_video):
    sp = conf().get('speed', {})
    rate = sp.get(job, DEFAULTS.get(job, 2.0))
    return rate * seconds_of_video


def learn(job, seconds_of_video, took):
    if seconds_of_video <= 0:
        return
    c = conf()
    sp = c.setdefault('speed', {})
    new = took / seconds_of_video
    sp[job] = round(new if job not in sp else .6 * sp[job] + .4 * new, 3)
    save_conf(c)


class Timer:
    def __init__(self, job, seconds_of_video):
        self.job, self.n = job, seconds_of_video

    def __enter__(self):
        self.t = time.time()
        return self

    def __exit__(self, *e):
        if not e[0]:
            learn(self.job, self.n, time.time() - self.t)


def transcribe(wav):
    """Word timestamps with whichever Whisper this computer has. Whisper sometimes 'hears' words in silence
    ("you", "Thank you."), which would turn a silent clip into a one-second video: words with no sound are dropped."""
    return [w for w in _whisper(wav) if _loud(wav, w['s'], w['e'])]


def _loud(wav, s, e, floor_db=-45):
    import wave, numpy as np
    if not hasattr(_loud, 'cache') or _loud.cache[0] != wav:
        with wave.open(wav) as f:
            _loud.cache = (wav, f.getframerate(), np.frombuffer(f.readframes(f.getnframes()), np.int16).astype(np.float32) / 32768)
    _, sr, a = _loud.cache
    seg = a[int(max(0, s - .05) * sr): int((e + .05) * sr)]
    if len(seg) < sr // 50:
        return True
    win = sr // 50  # loudest 20 ms inside the word
    n = len(seg) // win
    peak = float(np.sqrt((seg[:n * win].reshape(n, win) ** 2).mean(axis=1)).max()) if n else float(np.sqrt((seg ** 2).mean()))
    return 20 * np.log10(peak + 1e-10) > floor_db


def _whisper(wav):
    c = conf()
    if c.get('whisper') == 'mlx-whisper':
        import mlx_whisper
        d = mlx_whisper.transcribe(wav, path_or_hf_repo='mlx-community/whisper-large-v3-turbo', word_timestamps=True)
        return [dict(w=w['word'].strip(), s=round(float(w['start']), 3), e=round(float(w['end']), 3))
                for seg in d['segments'] for w in seg.get('words', []) if w['word'].strip()]
    from faster_whisper import WhisperModel
    m = WhisperModel('large-v3-turbo', compute_type='int8')

    def run(**kw):
        segs, _ = m.transcribe(wav, word_timestamps=True, **kw)
        return [dict(w=w.word.strip(), s=round(float(w.start), 3), e=round(float(w.end), 3)) for s in segs for w in s.words if w.word.strip()]
    try:
        return run()
    except IndexError:  # faster-whisper's word timing crashes on a segment with no alignable speech (screams, explosions)
        return run(vad_filter=True)


def jdump(obj, path):
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(obj, f, indent=1)


def log(msg):
    print(msg, flush=True)
    sys.stdout.flush()


def hexrgb(h, a=255):
    h = h.lstrip('#')
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4)) + (a,)


def VPY():
    return conf()['python']


def cookie_args():
    """Browser cookies for downloads that need a login (subscriber-only VODs). Only used when the user said yes,
    which sets "cookies_from" (for example "chrome") in the config."""
    b = conf().get('cookies_from')
    return ['--cookies-from-browser', b] if b else []


def _get(url, timeout=30):
    import urllib.request
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def hls_section(page_or_m3u8, a, b, out, audio_only=False, max_h=1080):
    """Seconds a..b of a long stream VOD, fetching only the 2-10 s pieces that cover them (a 40-hour VOD is fine).
    Takes a Twitch VOD page (the playlist is looked up) or a direct .m3u8 (Kick's VOD source). Writes a 16 kHz WAV
    when out ends in .wav, else an MP4. Returns a dict that says whether Twitch muted any of it for music (DMCA)."""
    import concurrent.futures as cf, re as _re, tempfile
    url = page_or_m3u8
    if '.m3u8' not in url:
        fmt = 'Audio_Only/ba/worst' if audio_only else f'best[height<={max_h}]/best'
        r = subprocess.run([VPY(), '-m', 'yt_dlp', '-q', '--no-warnings', '-g', '-f', fmt, *cookie_args(), url], capture_output=True, text=True)
        if r.returncode or not r.stdout.strip():
            raise SystemExit('DOWNLOAD_FAILED: could not open that VOD (subscriber-only, deleted, or still processing).')
        url = r.stdout.strip().splitlines()[0]
    text = _get(url).decode()
    if '#EXT-X-STREAM-INF' in text:  # a master list: pick the right quality
        best, lines = None, text.splitlines()
        for k, l in enumerate(lines):
            if l.startswith('#EXT-X-STREAM-INF'):
                h = int((_re.search(r'RESOLUTION=\d+x(\d+)', l) or [0, 0])[1] or 0)
                bw = int((_re.search(r'BANDWIDTH=(\d+)', l) or [0, 0])[1] or 0)
                key = (h <= max_h if not audio_only else True, -h if audio_only else h, bw if not audio_only else -bw)
                if best is None or key > best[0]:
                    best = (key, lines[k + 1].strip())
        url = best[1] if best[1].startswith('http') else url.rsplit('/', 1)[0] + '/' + best[1]
        text = _get(url).decode()
    base = url.split('?')[0].rsplit('/', 1)[0]
    t, segs, d = 0.0, [], None
    for l in text.splitlines():
        if l.startswith('#EXTINF:'):
            d = float(l[8:].split(',')[0])
        elif l and not l.startswith('#') and d is not None:
            if t + d > a and t < b:
                segs.append((t, l if l.startswith('http') else base + '/' + l))
            t += d; d = None
    if not segs:
        raise SystemExit(f'DOWNLOAD_FAILED: that time ({a:.0f} s) is past the end of the VOD ({t:.0f} s).')
    muted = any('-muted' in s for _, s in segs)
    tmp = tempfile.mkdtemp()
    with cf.ThreadPoolExecutor(6) as ex:
        datas = list(ex.map(lambda s: _get(s[1], 60), segs))
    ts = os.path.join(tmp, 'part.ts')
    with open(ts, 'wb') as f:
        for x in datas:
            f.write(x)
    ss = max(0.0, a - segs[0][0])
    if out.lower().endswith('.wav'):
        run(FF(), '-v', 'error', '-y', '-ss', f'{ss:.3f}', '-i', ts, '-t', f'{b - a:.3f}', '-vn', '-ar', '16000', '-ac', '1', out)
    else:
        run(FF(), '-v', 'error', '-y', '-ss', f'{ss:.3f}', '-i', ts, '-t', f'{b - a:.3f}', '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '17',
            '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-b:a', '192k', '-movflags', '+faststart', out)
    import shutil
    shutil.rmtree(tmp, ignore_errors=True)
    return dict(ok=os.path.exists(out), muted=muted)


_ffmpeg_on_path()
